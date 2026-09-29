from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    턱없네 회원. 일반 회원은 카카오 로그인으로만 가입하고, 관리자는 /admin/ 에서 로그인한다.

    - username: 카카오 닉네임이 한글이면 allauth가 영문 아이디(user, user2 ...)를 자동으로 만든다.
      그래서 화면에 보여줄 이름은 nickname 에 따로 저장한다.
    - 가입일(date_joined)은 AbstractUser에 이미 있음 → "가입 7일 미만 하향 제보는 검수 큐" 규칙에 사용 (기획 v2 7장)
    - 사업자등록번호 등 식별번호는 저장하지 않는다 (기획 v2 4.1)
    """

    NEW_ACCOUNT_DAYS = 7  # 이 기간 안의 계정은 판정 하향 제보가 관리자 검수로 감

    nickname = models.CharField("닉네임", max_length=30, blank=True)

    class Meta:
        verbose_name = "회원"
        verbose_name_plural = "회원"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.nickname or self.username

    def is_new_account(self, now=None):
        """가입한 지 NEW_ACCOUNT_DAYS일이 안 됐으면 True"""
        now = now or timezone.now()
        return now - self.date_joined < timedelta(days=self.NEW_ACCOUNT_DAYS)
