"""전시 포스터·큰 글씨 모드 테스트"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class PosterAndLargeTextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def test_poster_is_staff_only_and_links_map(self):
        url = reverse("ops:poster")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(User.objects.create_user(username="staff", is_staff=True))
        res = self.client.get(url)
        self.assertContains(res, 'data-qr="http://testserver/map/"')
        self.assertContains(res, "도움 받으면 들어갈 수 있어요")     # 문구는 판정 표시 상수에서
        self.assertContains(res, "아직 정보가 없어요")
        self.assertNotContains(res, "혼자 들어가기 어려워요")

    def test_every_page_has_large_text_toggle(self):
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, 'id="text-size-toggle"')
        self.assertContains(res, 'localStorage.getItem("teokeopne-large-text")')
