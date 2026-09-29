from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from places.models import Entrance, FieldDefinition
from places.tests import make_place, make_region

from .models import AccessibilityValue, Report, ReportConfirmation
from .selectors import current_values, pending_fields
from .services import reject_report, verify_report
from .signals import report_reviewed


class ReportTestBase(TestCase):
    def setUp(self):
        call_command("seed_base", stdout=StringIO())
        self.place = make_place(make_region("test"))
        self.entrance = Entrance.objects.create(place=self.place)
        self.user = User.objects.create_user(username="reporter")

    def report(self, status=Report.Status.VERIFIED, target=None, **values):
        target = target or self.entrance
        key = {"Entrance": "entrance", "Place": "place", "Building": "building"}[type(target).__name__]
        report = Report.objects.create(
            source=Report.Source.TEAM_SURVEY, status=status, created_by=self.user, **{key: target}
        )
        for field_key, raw in values.items():
            value = AccessibilityValue(report=report, field_id=field_key)
            value.set_value(raw)
            value.full_clean()
            value.save()
        return report


class ReportConstraintTests(ReportTestBase):
    def test_report_needs_exactly_one_target(self):
        for kwargs in ({}, {"place": self.place, "entrance": self.entrance}):
            with self.subTest(kwargs=kwargs), self.assertRaises(IntegrityError), transaction.atomic():
                Report.objects.create(source=Report.Source.USER_REPORT, **kwargs)


class AccessibilityValueTests(ReportTestBase):
    def test_set_value_by_type(self):
        report = self.report(step_height_cm="3.5", has_ramp="있음", door_type="자동문")
        values = {v.field_id: v for v in report.values.all()}
        self.assertEqual(values["step_height_cm"].value, Decimal("3.5"))
        self.assertIs(values["has_ramp"].value, True)
        self.assertEqual(values["door_type"].value, "자동문")
        self.assertEqual(str(values["step_height_cm"]), "입구 단차: 3.5 cm")

    def test_invalid_values_rejected(self):
        report = self.report()
        cases = [
            ("step_height_cm", "높음"),     # 숫자 아님
            ("step_height_cm", "-1"),       # 음수
            ("door_type", "창문"),          # 선택지에 없음
            ("interior_step", True),        # 장소 필드를 출입구 제보에 넣음
        ]
        for key, raw in cases:
            with self.subTest(key=key, raw=raw), self.assertRaises(ValidationError):
                value = AccessibilityValue(report=report, field=FieldDefinition.objects.get(key=key))
                value.set_value(raw)
                value.full_clean()


class CurrentValuesTests(ReportTestBase):
    def test_uses_latest_verified_only(self):
        self.report(step_height_cm=30)                                        # 예전 답사
        self.report(step_height_cm=0)                                         # 최신 답사 (경사로 설치 후)
        self.report(status=Report.Status.PENDING, step_height_cm=50)          # 확인 전 제보 → 판정에 안 씀
        self.report(status=Report.Status.REJECTED, step_height_cm=99)         # 반려 → 안 씀

        values = current_values(self.entrance)
        self.assertEqual(values["step_height_cm"].value, Decimal("0"))
        self.assertEqual(pending_fields(self.entrance), {"step_height_cm"})

    def test_targets_are_separate(self):
        self.report(step_height_cm=3)
        self.report(target=self.place, interior_step=True)
        self.assertEqual(set(current_values(self.entrance)), {"step_height_cm"})
        self.assertEqual(set(current_values(self.place)), {"interior_step"})


class ReviewServiceTests(ReportTestBase):
    def test_verify_sets_fields_and_sends_signal_after_commit(self):
        received = []
        report_reviewed.connect(lambda sender, report, **kw: received.append(report.pk), weak=False, dispatch_uid="t")
        self.addCleanup(report_reviewed.disconnect, dispatch_uid="t")
        admin = User.objects.create_user(username="admin", is_staff=True)
        report = self.report(status=Report.Status.PENDING, step_height_cm=2)

        with self.captureOnCommitCallbacks(execute=True):
            verify_report(report, by=admin)

        report.refresh_from_db()
        self.assertEqual((report.status, report.reviewed_by), (Report.Status.VERIFIED, admin))
        self.assertIsNotNone(report.reviewed_at)
        self.assertEqual(received, [report.pk])

    def test_reject_keeps_reason(self):
        report = self.report(status=Report.Status.PENDING, step_height_cm=2)
        reject_report(report, reason="사진이 흐려요")
        report.refresh_from_db()
        self.assertEqual((report.status, report.reject_reason), (Report.Status.REJECTED, "사진이 흐려요"))

    def test_cannot_confirm_own_report(self):
        report = self.report(status=Report.Status.PENDING, step_height_cm=2)
        with self.assertRaises(ValidationError):
            ReportConfirmation(report=report, user=self.user).clean()
        ReportConfirmation(report=report, user=User.objects.create_user(username="other")).clean()


class NewPlaceReportTests(ReportTestBase):
    def test_new_place_needs_name(self):
        Report.objects.create(source=Report.Source.USER_REPORT, suggested_name="월계시장 입구 카페", location_text="시장 정문 옆")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Report.objects.create(source=Report.Source.USER_REPORT, location_text="이름 없음")

    def test_new_place_takes_entrance_fields(self):
        report = Report.objects.create(source=Report.Source.USER_REPORT, suggested_name="새 가게")
        self.assertTrue(report.is_new_place)
        self.assertEqual(report.target_label, "새 장소: 새 가게")
        value = AccessibilityValue(report=report, field=FieldDefinition.objects.get(key="step_height_cm"))
        value.set_value(3)
        value.full_clean()  # 입구 필드는 가능
        with self.assertRaises(ValidationError):
            AccessibilityValue(report=report, field=FieldDefinition.objects.get(key="interior_step"), value_bool=True).full_clean()


class ObservedAtTests(ReportTestBase):
    def test_latest_observation_wins_not_latest_input(self):
        from datetime import timedelta

        from django.utils import timezone

        recent = self.report(step_height_cm=0)                 # 어제 현장 확인
        old = self.report(step_height_cm=30)                   # 나중에 입력했지만 작년 답사 기록
        Report.objects.filter(pk=recent.pk).update(observed_at=timezone.now() - timedelta(days=1))
        Report.objects.filter(pk=old.pk).update(observed_at=timezone.now() - timedelta(days=365))
        self.assertEqual(current_values(self.entrance)["step_height_cm"].value, Decimal("0"))
