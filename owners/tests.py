"""사장님 기능 테스트 (기획 v2 4·6장)"""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from judgments.engine import recompute_place
from judgments.models import Judgment
from judgments.services import required_confirmations
from places.models import Entrance, Region
from places.tests import make_place
from reports.models import AccessibilityValue, Report
from reports.services import confirm_report
from reports.test_views import TempMediaMixin, photo

from .models import ClaimCode, OwnerClaim, OwnerResponse, PlaceViewStat, SupportProgram, VisitWish
from .services import OwnerError, claim_with_code, ramp_guide


class OwnerTestBase(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.region = Region.objects.get(code="wolgye1")
        self.place = make_place(self.region, "계단 약국")
        self.door = Entrance.objects.create(place=self.place, name="정문")
        report = Report.objects.create(source="TEAM_SURVEY", status="VERIFIED", entrance=self.door)
        for key, raw in {"step_height_cm": 15, "step_count": 1, "door_width_cm": 90, "has_ramp": False}.items():
            v = AccessibilityValue(report=report, field_id=key)
            v.set_value(raw)
            v.save()
        recompute_place(self.place)                       # 휠체어: 혼자 들어가기 어려워요
        self.owner = User.objects.create_user(username="owner")
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.neighbor = User.objects.create_user(username="neighbor")

    def approved_owner(self):
        claim = claim_with_code(self.owner, ClaimCode.issue(place=self.place).code)
        claim.review(OwnerClaim.Status.APPROVED, self.staff)
        self.client.force_login(self.owner)


class ClaimTests(OwnerTestBase):
    def test_claim_with_code_then_staff_approves(self):
        code = ClaimCode.issue(place=self.place)
        self.client.force_login(self.owner)
        self.assertContains(self.client.post(reverse("owners:claim"), {"code": "000000" if code.code != "000000" else "111111"}),
                            "코드를 찾을 수 없어요")
        self.client.post(reverse("owners:claim"), {"code": code.code})
        claim = OwnerClaim.objects.get(user=self.owner)
        self.assertEqual((claim.status, claim.role), ("PENDING", "OPERATOR"))
        self.assertFalse(OwnerClaim.is_owner(self.owner, self.place))          # 승인 전
        self.assertEqual(self.client.get(reverse("owners:dashboard", args=[self.place.pk])).status_code, 302)

        self.client.force_login(self.staff)
        self.client.post(reverse("ops:claims"), {"claim": claim.pk, "action": "approve"})
        self.assertTrue(OwnerClaim.is_owner(self.owner, self.place))

    def test_code_is_single_use(self):
        code = ClaimCode.issue(place=self.place)
        claim_with_code(self.owner, code.code)
        with self.assertRaises(OwnerError):
            claim_with_code(self.neighbor, code.code)

    def test_staff_issues_code_on_place_page(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("ops:claim-code", args=[self.place.pk]))
        code = ClaimCode.objects.get(place=self.place)
        self.assertRegex(code.code, r"^\d{6}$")
        self.assertContains(self.client.get(reverse("ops:place-edit", args=[self.place.pk])), code.code)


class ResponseAndDeclarationTests(OwnerTestBase):
    def test_response_is_public_immediately(self):
        self.approved_owner()
        self.client.post(reverse("owners:response", args=[self.place.pk]), {
            "owner_comment": "언제든 말씀 주세요", "assistance_contact": "입구 호출벨", "assistance_hours": "영업시간 내내",
            "alt_entrance": "",
        })
        res = self.client.get(reverse("places:detail", args=[self.place.pk]))
        self.assertContains(res, "언제든 말씀 주세요")
        self.assertContains(res, "사장님이 알려준 들어가는 방법")
        self.assertContains(res, "도움 요청: 입구 호출벨 (영업시간 내내)")

    def test_declaration_needs_photo_and_one_confirmation(self):
        self.approved_owner()
        url = reverse("owners:declaration", args=[self.place.pk])
        data = {"assistance_offered": "true", "portable_ramp": "true", "portable_ramp_length_cm": "120"}
        self.assertEqual(self.client.post(url, data).status_code, 200)            # 사진 없음
        self.assertContains(self.client.post(url, {**data, "portable_ramp_length_cm": "", "photo": photo()}),
                            "경사로 길이를 적어 주세요")
        self.client.post(url, {**data, "photo": photo()})
        report = Report.objects.get(source="OWNER")
        self.assertEqual((report.status, report.place), ("PENDING", self.place))
        self.assertEqual(required_confirmations(report), 1)
        # 선언만으로는 판정이 올라가지 않음
        self.assertEqual(Judgment.objects.get(place=self.place, profile="WHEELCHAIR").result, "DIFFICULT")

        with self.captureOnCommitCallbacks(execute=True):
            confirm_report(report, self.neighbor, required_confirmations(report))
        self.assertEqual(Judgment.objects.get(place=self.place, profile="WHEELCHAIR").result, "CONDITIONAL")  # 15 ≤ 120÷8
        self.assertContains(self.client.get(reverse("places:detail", args=[self.place.pk])), "도움 제공 가게")

    def test_non_owner_blocked(self):
        self.client.force_login(self.neighbor)
        res = self.client.get(reverse("owners:declaration", args=[self.place.pk]))
        self.assertRedirects(res, reverse("owners:home"))


class CorrectionTests(OwnerTestBase):
    def test_correction_needs_two_and_shows_pending_label(self):
        self.approved_owner()
        url = reverse("owners:correction", args=[self.place.pk])
        res = self.client.post(url, {"field": "has_ramp", "value": "모름", "photo": photo()})
        self.assertIn("'있음' 또는 '없음'", res.context["form"].errors["value"][0])
        self.client.post(url, {"field": "step_height_cm", "value": "3", "photo": photo(), "note": "턱을 깎았어요"})
        report = Report.objects.get(source="OWNER")
        self.assertEqual(report.entrance, self.door)                                # 입구 항목 → 주 출입구
        self.assertEqual(required_confirmations(report), 2)
        self.assertContains(self.client.get(reverse("places:detail", args=[self.place.pk])),
                            "사장님이 정정을 요청했어요 (확인 중)")
        # 같은 항목은 진행 중인 요청이 끝나야 다시
        self.assertContains(self.client.post(url, {"field": "step_height_cm", "value": "2", "photo": photo()}),
                            "아직 확인 중")

    def test_ops_list_labels_owner_requests(self):
        self.approved_owner()
        self.client.post(reverse("owners:correction", args=[self.place.pk]),
                         {"field": "step_height_cm", "value": "3", "photo": photo()})
        Report.objects.filter(source="OWNER").update(created_at=timezone.now() - timedelta(days=8))
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("ops:reports")), "사장님 정정 요청")
        self.assertContains(self.client.get(reverse("ops:dashboard")), "7일 넘게 처리하지 않은 사장님 요청이 1건")


class DemandTests(OwnerTestBase):
    def test_wish_only_on_difficult_and_counted(self):
        detail = reverse("places:detail", args=[self.place.pk])
        self.client.force_login(self.neighbor)
        # 단차 15cm·계단 1칸: 휠체어만 '어려움' → 가고 싶어요 버튼은 휠체어에만
        res = self.client.get(detail)
        self.assertContains(res, 'name="profile" value="WHEELCHAIR"', count=1)
        self.assertNotContains(res, 'name="profile" value="STROLLER"')
        self.client.post(reverse("owners:wish", args=[self.place.pk]), {"profile": "WHEELCHAIR", "next": detail})
        self.assertTrue(VisitWish.objects.filter(user=self.neighbor, profile="WHEELCHAIR").exists())
        self.client.post(reverse("owners:wish", args=[self.place.pk]), {"profile": "WHEELCHAIR", "next": detail})
        self.assertFalse(VisitWish.objects.exists())                             # 다시 누르면 취소

    def test_view_stats_once_per_session_day(self):
        detail = reverse("places:detail", args=[self.place.pk])
        self.client.get(detail, {"profile": "STROLLER"})
        self.client.get(detail, {"profile": "STROLLER"})                         # 새로고침
        self.client.get(detail)                                                  # 조건 없이 들어오면 세지 않음
        self.assertEqual(PlaceViewStat.objects.get(place=self.place, profile="STROLLER").count, 1)

    def test_dashboard_numbers_and_ramp_guide(self):
        VisitWish.objects.create(user=self.neighbor, place=self.place, profile_id="WHEELCHAIR")
        PlaceViewStat.objects.create(place=self.place, profile_id="WHEELCHAIR", date=timezone.localdate(), count=42)
        SupportProgram.objects.create(region=self.region, title="소규모시설 경사로 설치 지원", target_desc="1층 가게")
        self.assertEqual(ramp_guide(self.place)["ramp_cm"], 120)                 # 단차 15cm × 8
        self.approved_owner()
        res = self.client.get(reverse("owners:dashboard", args=[self.place.pk]))
        self.assertContains(res, "이동 조건별 조회 42번 · \"가고 싶어요\" 1명")
        self.assertContains(res, "약 120cm 이상")
        self.assertContains(res, "소규모시설 경사로 설치 지원")
        self.assertContains(res, "법 위반 여부를 판단한 것이 아니에요")          # OP-8


class SupportPageTests(OwnerTestBase):
    def test_only_active_programs(self):
        SupportProgram.objects.create(region=self.region, title="올해 사업", target_desc="대상")
        SupportProgram.objects.create(region=self.region, title="지난 사업", target_desc="대상", is_active=False)
        res = self.client.get(reverse("owners:support"))
        self.assertContains(res, "올해 사업")
        self.assertNotContains(res, "지난 사업")

    def test_owner_response_model_has_content(self):
        self.assertFalse(OwnerResponse(place=self.place).has_content)
