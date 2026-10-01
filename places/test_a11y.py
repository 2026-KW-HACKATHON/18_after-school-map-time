"""스크린리더·키보드 사용 기본 장치 (Could "스크린리더·음성 안내")"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse


class AccessibilityHooksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def test_skip_link_and_main_target_on_every_page(self):
        for url in (reverse("places:map"), reverse("places:search"), reverse("owners:support")):
            res = self.client.get(url)
            self.assertContains(res, '<a class="skip-link" href="#main">본문 바로가기</a>', html=False)
            self.assertContains(res, 'id="main"')

    def test_map_has_named_regions_and_text_alternative(self):
        res = self.client.get(reverse("places:map"))
        self.assertContains(res, 'aria-label="지도. 같은 장소를 목록에서도 볼 수 있어요"')
        self.assertContains(res, 'aria-label="장소 미리 보기"')
        self.assertContains(res, 'id="list-status" class="muted small" aria-live="polite"')   # 목록 개수 변화를 읽어 줌
        self.assertContains(res, '<h1 class="sr-only">')
