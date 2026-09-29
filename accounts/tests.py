from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .adapters import SocialAccountAdapter
from .models import User

TEST_PROVIDERS = {"kakao": {"APPS": [{"client_id": "test-rest-key", "secret": "", "key": ""}]}}


class UserModelTests(TestCase):
    def test_display_name_prefers_nickname(self):
        self.assertEqual(User(username="user2", nickname="턱없이").display_name, "턱없이")
        self.assertEqual(User(username="user2").display_name, "user2")

    def test_is_new_account_boundary(self):
        now = timezone.now()
        user = User(username="u", date_joined=now - timedelta(days=7) + timedelta(seconds=1))
        self.assertTrue(user.is_new_account(now))      # 7일이 안 됨
        user.date_joined = now - timedelta(days=7)
        self.assertFalse(user.is_new_account(now))     # 정확히 7일 → 새 계정 아님


class KakaoLoginTests(TestCase):
    def test_login_page_has_only_kakao(self):
        res = self.client.get(reverse("account_login"))
        self.assertContains(res, "카카오로 시작하기")
        self.assertNotContains(res, 'type="password"')  # 아이디·비밀번호 로그인 없음

    @override_settings(SOCIALACCOUNT_PROVIDERS=TEST_PROVIDERS)
    def test_kakao_login_redirects_to_kakao_authorize(self):
        res = self.client.post(reverse("kakao_login"))
        self.assertEqual(res.status_code, 302)
        url = urlparse(res["Location"])
        self.assertEqual(url.netloc, "kauth.kakao.com")
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], ["test-rest-key"])
        self.assertTrue(query["redirect_uri"][0].endswith("/accounts/kakao/login/callback/"))

    def test_adapter_saves_kakao_nickname(self):
        account = SocialAccount(
            provider="kakao",
            uid="123",
            extra_data={"kakao_account": {"profile": {"nickname": "월계동주민"}}},
        )
        sociallogin = SocialLogin(account=account, user=User())
        request = RequestFactory().get("/")
        user = SocialAccountAdapter().populate_user(request, sociallogin, {"username": "월계동주민"})
        self.assertEqual(user.nickname, "월계동주민")


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", nickname="테스터")
        self.client.force_login(self.user)

    def test_nav_shows_nickname_and_logout(self):
        res = self.client.get(reverse("core:home"))
        self.assertContains(res, "테스터님")
        self.assertContains(res, "로그아웃")

    def test_logout_post(self):
        res = self.client.post(reverse("account_logout"))
        self.assertRedirects(res, "/", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
