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


class Notification(models.Model):
    """
    서비스 안 알림 (외부 발송 없음 → 비용 없음). 상단 메뉴에 안 읽은 개수, /notifications/ 에서 확인.
    만드는 곳은 accounts/notify.py 한 곳 — 제보·사장님 요청 처리 결과, 인증 결과, 가고 싶어요 가게 개선
    """

    class Kind(models.TextChoices):
        REPORT = "REPORT", "제보 결과"
        OWNER_REQUEST = "OWNER_REQUEST", "사장님·건물주 요청 결과"
        CLAIM = "CLAIM", "인증 결과"
        WISH = "WISH", "가고 싶어요 가게 소식"

    user = models.ForeignKey("accounts.User", verbose_name="받는 사람", on_delete=models.CASCADE,
                             related_name="notifications")
    kind = models.CharField("종류", max_length=20, choices=Kind.choices)
    message = models.CharField("내용", max_length=200)
    url = models.CharField("링크", max_length=200, blank=True)
    created_at = models.DateTimeField("만든 시각", default=timezone.now)
    read_at = models.DateTimeField("읽은 시각", null=True, blank=True)

    class Meta:
        verbose_name = "알림"
        verbose_name_plural = "알림"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"], name="notification_user_unread")]

    def __str__(self):
        return f"{self.user} · {self.message}"

    @property
    def is_read(self):
        return self.read_at is not None
