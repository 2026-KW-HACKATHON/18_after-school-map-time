"""운영자 화면 검토 대기 폴링 (10초마다 ops/api/pending/)"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from reports.models import Report


class PendingPollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())

    def setUp(self):
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.url = reverse("ops:pending-status")

    def test_staff_only_json_counts(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(User.objects.create_user(username="jumin"))
        self.assertEqual(self.client.get(self.url).status_code, 302)
        Report.objects.create(source="USER_REPORT", status="PENDING", suggested_name="새 가게")
        Report.objects.create(source="TEAM_SURVEY", status="PENDING", suggested_name="답사")   # 검토 대상 아님
        self.client.force_login(self.staff)
        res = self.client.get(self.url)
        self.assertEqual(res.json(), {"pending": 1, "claims": 0})
        self.assertEqual(res["Cache-Control"], "no-store")

    def test_nav_carries_start_counts_and_script(self):
        Report.objects.create(source="USER_REPORT", status="PENDING", suggested_name="새 가게")
        self.client.force_login(self.staff)
        res = self.client.get(reverse("ops:dashboard"))
        self.assertContains(res, f'data-pending-url="{self.url}" data-pending="1" data-claims="0"')
        self.assertContains(res, "ops/js/pending-poll")
        self.assertContains(res, 'id="ops-new-banner"')
