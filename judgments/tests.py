"""
판정 엔진 테스트. 기준값은 judgments/data/rules_v1.json(초안)에서 읽는다.
판정 기준표가 확정돼 수치가 바뀌면 경계값 테스트의 숫자도 같이 바꾼다.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from places.models import Building, Entrance
from places.tests import make_place, make_region
from reports.models import AccessibilityValue, Report
from reports.services import verify_report

from .engine import judge, recompute_place
from .models import ConditionProfile, Judgment, Outcome, Rule, RuleCondition, RuleSet


class JudgmentTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())
        cls.wheelchair = ConditionProfile.objects.get(key="WHEELCHAIR")
        cls.stroller = ConditionProfile.objects.get(key="STROLLER")

    def setUp(self):
        self.region = make_region("test")
        self.place = make_place(self.region)
        self.door = Entrance.objects.create(place=self.place, name="정문")

    def values(self, target, status=Report.Status.VERIFIED, **values):
        key = {"Entrance": "entrance", "Place": "place", "Building": "building"}[type(target).__name__]
        report = Report.objects.create(source=Report.Source.TEAM_SURVEY, status=status, **{key: target})
        for field_key, raw in values.items():
            v = AccessibilityValue(report=report, field_id=field_key)
            v.set_value(raw)
            v.save()
        return report

    def judge(self, profile=None):
        return judge(self.place, profile or self.wheelchair)


class ThresholdBoundaryTests(JudgmentTestBase):
    def test_step_2cm_accessible_2_1cm_not(self):
        self.values(self.door, step_height_cm="2", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.ACCESSIBLE)

        self.values(self.door, step_height_cm="2.1", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.DIFFICULT)

    def test_portable_ramp_step_equals_length_div_8(self):
        # 이동식 경사로 120cm → 올라갈 수 있는 단차 15cm
        self.values(self.place, portable_ramp=True, portable_ramp_length_cm=120, assistance_offered=True)
        self.values(self.door, step_height_cm="15", door_width_cm=90, has_ramp=False)
        result = self.judge()
        self.assertEqual(result.outcome, Outcome.CONDITIONAL)
        self.assertEqual(result.rule.basis, Rule.Basis.APPLIED)

        self.values(self.door, step_height_cm="15.1", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.DIFFICULT)

    def test_assistance_without_ramp_stays_difficult(self):
        # 기획 v2 4.2: 경사로 없이 들어 올리는 도움은 판정에 넣지 않음
        self.values(self.place, assistance_offered=True)
        self.values(self.door, step_height_cm="15", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.DIFFICULT)

    def test_pending_owner_declaration_not_used(self):
        # 사장님 선언만으로는 판정이 올라가지 않음 (사진 확인 = VERIFIED 전까지)
        self.values(self.place, status=Report.Status.PENDING,
                    portable_ramp=True, portable_ramp_length_cm=120, assistance_offered=True)
        self.values(self.door, step_height_cm="15", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.DIFFICULT)


class UnknownAndRoutesTests(JudgmentTestBase):
    def test_no_entrance_is_unknown(self):
        self.door.delete()
        self.assertEqual(self.judge().outcome, Outcome.UNKNOWN)

    def test_missing_value_is_unknown_not_difficult(self):
        self.values(self.door, step_height_cm="1")  # 문 폭을 모름
        self.assertEqual(self.judge().outcome, Outcome.UNKNOWN)

    def test_best_route_is_alternative_entrance(self):
        back = Entrance.objects.create(place=self.place, name="주차장 쪽 문", is_main=False)
        self.values(self.door, step_height_cm="30", step_count=2, door_width_cm=90, has_ramp=False)
        self.values(back, step_height_cm="0", door_width_cm=90, has_ramp=False)
        result = self.judge()
        self.assertEqual((result.outcome, result.entrance), (Outcome.ACCESSIBLE, back))

    def test_difficult_plus_unknown_route_is_unknown(self):
        # 모르는 출입구가 남아 있으면 어려움으로 단정하지 않음
        Entrance.objects.create(place=self.place, name="뒷문", is_main=False)
        self.values(self.door, step_height_cm="30", door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().outcome, Outcome.UNKNOWN)

    def test_upper_floor_uses_building_entrance(self):
        building = Building.objects.create(region=self.region, address="월계동 1", lat=Decimal("37.62"), lng=Decimal("127.05"))
        self.place.building, self.place.floor = building, 2
        self.place.save()
        lobby = Entrance.objects.create(building=building, name="건물 입구")
        self.values(self.door, step_height_cm="0", door_width_cm=90, has_ramp=False)       # 가게 문은 괜찮은데
        self.values(lobby, step_height_cm="45", step_count=3, door_width_cm=120, has_ramp=False)  # 건물 입구 계단
        result = self.judge()
        self.assertEqual((result.outcome, result.entrance), (Outcome.DIFFICULT, lobby))

    def test_difficult_has_fact_line(self):
        self.values(self.door, step_height_cm="30", step_count=2, door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge().reason, "입구 단차 30cm · 계단 수 2칸")

    def test_profiles_differ(self):
        # 계단 한 칸 15cm: 휠체어 어려움, 유아차는 들어 올리면 가능 (조건부)
        self.values(self.door, step_height_cm="15", step_count=1, door_width_cm=90, has_ramp=False)
        self.assertEqual(self.judge(self.wheelchair).outcome, Outcome.DIFFICULT)
        self.assertEqual(self.judge(self.stroller).outcome, Outcome.CONDITIONAL)


class ExtensibilityTests(JudgmentTestBase):
    def test_new_profile_by_data_only(self):
        """새 이동 조건(캐리어)을 코드 수정 없이 DB 행 추가만으로 판정 (기획 v2 8장)"""
        suitcase = ConditionProfile.objects.create(key="SUITCASE", label="캐리어", order=50)
        rule = Rule.objects.create(
            rule_set=RuleSet.active(), profile=suitcase, outcome=Outcome.ACCESSIBLE, priority=10, basis=Rule.Basis.TEAM
        )
        RuleCondition.objects.create(rule=rule, field_id="step_count", operator="LTE", threshold=0)
        self.values(self.door, step_height_cm="3", step_count=0, door_width_cm=90, has_ramp=False)

        judgments = {j.profile_id: j.result for j in recompute_place(self.place)}
        self.assertEqual(judgments["SUITCASE"], Outcome.ACCESSIBLE)
        self.assertEqual(judgments["WHEELCHAIR"], Outcome.DIFFICULT)  # 3cm 턱

    def test_only_one_active_ruleset(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RuleSet.objects.create(version=99, is_active=True)


class RecomputeTests(JudgmentTestBase):
    def test_saves_rule_version_and_improvement_badge(self):
        self.values(self.door, step_height_cm="30", door_width_cm=90, has_ramp=False)
        recompute_place(self.place)
        j = Judgment.objects.get(place=self.place, profile=self.wheelchair)
        self.assertEqual((j.result, j.rule_version, j.has_improved_badge), (Outcome.DIFFICULT, 1, False))

        # 경사로 설치 후 재답사 → 판정 상승 → "개선 완료" 배지
        self.values(self.door, step_height_cm="30", door_width_cm=90, has_ramp=True)
        recompute_place(self.place)
        j.refresh_from_db()
        self.assertEqual(j.result, Outcome.ACCESSIBLE)
        self.assertTrue(j.has_improved_badge)

        # 다시 내려가면 배지만 숨김 (개선 기록은 유지)
        self.values(self.door, step_height_cm="30", door_width_cm=90, has_ramp=False)
        recompute_place(self.place)
        j.refresh_from_db()
        self.assertFalse(j.has_improved_badge)
        self.assertIsNotNone(j.improved_at)

    def test_verifying_report_recomputes(self):
        report = self.values(self.door, status=Report.Status.PENDING, step_height_cm="0", door_width_cm=90, has_ramp=False)
        with self.captureOnCommitCallbacks(execute=True):
            verify_report(report)
        self.assertEqual(Judgment.objects.get(place=self.place, profile=self.wheelchair).result, Outcome.ACCESSIBLE)

    def test_recompute_command(self):
        self.values(self.door, step_height_cm="0", door_width_cm=90, has_ramp=False)
        out = StringIO()
        call_command("recompute_judgments", "--region", "test", stdout=out)
        self.assertIn("1곳", out.getvalue())
        self.assertEqual(Judgment.objects.filter(place=self.place).count(), ConditionProfile.objects.count())
