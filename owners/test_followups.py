"""정보 충돌 안내(기획 v2 7장)·가고 싶어요 개선 알림(6.2)·구청용 지역 집계(8장) 테스트"""

from django.urls import reverse

from judgments.engine import recompute_place
from reports.models import Report
from reports.services import verify_report
from reports.test_views import photo

from .models import VisitWish
from .test_owner_ux import survey
from .tests import OwnerTestBase


class ConflictNoticeTests(OwnerTestBase):
    def test_owner_and_resident_values_differ(self):
        detail = reverse("places:detail", args=[self.place.pk])
        survey({"entrance": self.door}, {"step_height_cm": 15}, source="USER_REPORT")   # 주민 제보(반영됨)
        self.assertNotContains(self.client.get(detail), "정보가 서로 달라요")

        self.approved_owner()
        self.client.post(reverse("owners:correction", args=[self.place.pk]),
                         {"field": "step_height_cm", "value": "3", "photo": photo()})   # 사장님 정정(확인 중)
        res = self.client.get(detail)
        self.assertContains(res, "정보가 서로 달라요")
        self.assertContains(res, "입구 단차")

        # 운영진이 판단(승인)하면 사라짐
        report = Report.objects.get(source="OWNER")
        with self.captureOnCommitCallbacks(execute=True):
            verify_report(report, by=self.staff)
        self.assertNotContains(self.client.get(detail), "정보가 서로 달라요")

    def test_team_survey_vs_owner_is_not_conflict(self):
        """충돌은 사장님 정보와 주민 제보 사이만 (팀 답사와 다르면 일반 정정 요청)"""
        self.approved_owner()
        self.client.post(reverse("owners:correction", args=[self.place.pk]),
                         {"field": "step_height_cm", "value": "3", "photo": photo()})
        self.assertNotContains(self.client.get(reverse("places:detail", args=[self.place.pk])), "정보가 서로 달라요")


class WishImprovedTests(OwnerTestBase):
    def test_menu_and_page_tell_when_wished_place_improves(self):
        self.client.force_login(self.neighbor)
        self.assertNotContains(self.client.get(reverse("places:map")), reverse("owners:wishes"))  # 누른 적 없음
        VisitWish.objects.create(user=self.neighbor, place=self.place, profile_id="WHEELCHAIR")
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, f'href="{reverse("owners:wishes")}" class="nav-wide"')
        self.assertNotContains(res, "좋아진 곳")

        # 경사로 설치 후 재답사 → 판정 상승
        survey({"entrance": self.door}, {"has_ramp": True})
        recompute_place(self.place)
        self.assertContains(self.client.get(reverse("places:map")), "좋아진 곳 1")
        page = self.client.get(reverse("owners:wishes"))
        self.assertContains(page, "계단 약국")
        self.assertContains(page, "좋아졌어요")


class DistrictTests(OwnerTestBase):
    def test_staff_only_summary_candidates_and_csv(self):
        VisitWish.objects.create(user=self.neighbor, place=self.place, profile_id="WHEELCHAIR")
        self.approved_owner()                                        # 사장님 인증 = 개선 의지
        url = reverse("ops:district")
        self.assertEqual(self.client.get(url).status_code, 302)      # 사장님은 못 봄

        self.client.force_login(self.staff)
        res = self.client.get(url)
        self.assertContains(res, "경사로 지원사업 검토 목록")
        self.assertContains(res, "계단 약국")
        self.assertContains(res, "약 120cm")                          # 단차 15cm × 8
        row = res.context["candidates"][0]
        self.assertEqual((row["wishes"], row["owner"], row["profiles"]), (1, True, ["휠체어"]))
        wheelchair = next(r for r in res.context["distribution"] if r["profile"].key == "WHEELCHAIR")
        self.assertEqual([c["count"] for c in wheelchair["cells"]], [0, 0, 1, 0])

        csv_res = self.client.get(reverse("ops:district-csv"))
        body = csv_res.content.decode("utf-8")
        self.assertTrue(body.startswith("﻿가게,주소"))
        self.assertIn("계단 약국", body)
