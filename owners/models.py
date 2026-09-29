"""
사장님·건물주 기능 (기획 v2 4·5·6장, dev-plan-v2 D6·D7·D8).

- 인증: 팀 답사 때 가게에 6자리 코드(ClaimCode)를 전달 → 사장님이 입력(OwnerClaim) → 운영자 승인
  사업자등록번호 등 식별번호는 받지 않는다 (기획 v2 4.1, 12장 7번)
- 사장님 한마디·도움 요청 방법(OwnerResponse)은 안내 문구라 바로 보인다
- 판정에 쓰이는 값(도움 제공·이동식 경사로)과 정정 요청은 '사장님 출처 제보'(reports.Report, source=OWNER)로
  들어가서 사진 확인을 거친다 → 사장님 선언만으로 판정이 올라가지 않음 (기획 v2 4.2)
- 가고 싶어요(VisitWish)·조회 수(PlaceViewStat)는 사장님 대시보드의 "잠재 손님" 숫자 (기획 v2 4.5)
- 지원사업(SupportProgram)은 매년 바뀌므로 코드가 아닌 데이터로 (기획 v2 6.3)
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from judgments.models import ConditionProfile
from places.models import Building, Place, Region


def _new_code():
    # 6자리 숫자 (전화로 불러주기 쉽게)
    return f"{secrets.randbelow(1_000_000):06d}"


class ClaimCode(models.Model):
    """인증 코드 (1회용). 운영자가 발급해서 답사 때 가게에 전달"""

    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, null=True, blank=True, related_name="claim_codes")
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.CASCADE, null=True, blank=True, related_name="claim_codes"
    )
    code = models.CharField("코드", max_length=6, unique=True, default=_new_code)
    created_at = models.DateTimeField("발급일", auto_now_add=True)
    used_at = models.DateTimeField("사용일", null=True, blank=True)

    class Meta:
        verbose_name = "인증 코드"
        verbose_name_plural = "인증 코드"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(place__isnull=False, building__isnull=True)
                | models.Q(place__isnull=True, building__isnull=False),
                name="claim_code_for_place_or_building",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.place or self.building})"

    @property
    def is_used(self):
        return self.used_at is not None

    @classmethod
    def issue(cls, place=None, building=None):
        """겹치지 않는 코드로 발급"""
        while True:
            code = _new_code()
            if not cls.objects.filter(code=code).exists():
                return cls.objects.create(place=place, building=building, code=code)


class OwnerClaim(models.Model):
    """사장님·건물주 인증 신청. 운영자가 승인하면 권한이 생긴다"""

    class Role(models.TextChoices):
        OPERATOR = "OPERATOR", "가게 사장님"
        BUILDING_OWNER = "BUILDING_OWNER", "건물주"

    class Status(models.TextChoices):
        PENDING = "PENDING", "확인 중"
        APPROVED = "APPROVED", "승인됨"
        REJECTED = "REJECTED", "반려됨"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="신청자", on_delete=models.CASCADE, related_name="owner_claims")
    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, null=True, blank=True, related_name="owner_claims")
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.CASCADE, null=True, blank=True, related_name="owner_claims"
    )
    role = models.CharField("구분", max_length=20, choices=Role.choices)
    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.PENDING)
    code = models.ForeignKey(ClaimCode, verbose_name="사용한 코드", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField("신청일", auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="처리자", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField("처리일", null=True, blank=True)
    reject_reason = models.CharField("반려 사유", max_length=200, blank=True)

    class Meta:
        verbose_name = "사장님·건물주 인증"
        verbose_name_plural = "사장님·건물주 인증"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.place or self.building} ({self.get_status_display()})"

    @classmethod
    def is_owner(cls, user, place):
        """이 사람이 이 가게의 승인된 사장님인가"""
        if not user.is_authenticated:
            return False
        return cls.objects.filter(user=user, place=place, status=cls.Status.APPROVED).exists()

    def review(self, status, by, reason=""):
        self.status, self.reviewed_by, self.reviewed_at, self.reject_reason = status, by, timezone.now(), reason
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "reject_reason"])


class OwnerResponse(models.Model):
    """
    사장님 한마디·도움 요청 방법 (기획 v2 4.2 안내용 항목). 판정에는 쓰지 않으므로 바로 공개된다.
    """

    place = models.OneToOneField(Place, verbose_name="장소", on_delete=models.CASCADE, related_name="owner_response")
    assistance_contact = models.CharField("도움 요청 방법", max_length=100, blank=True, help_text="예: 입구 호출벨, 전화 02-000-0000")
    assistance_hours = models.CharField("도움 가능 시간", max_length=100, blank=True, help_text="예: 영업시간 내내, 14~17시 제외")
    alt_entrance = models.CharField("다른 출입구 안내", max_length=200, blank=True, help_text="예: 건물 뒤편 주차장 쪽 문은 턱이 없어요")
    owner_comment = models.CharField("사장님 한마디", max_length=200, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="작성자", on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        verbose_name = "사장님 한마디"
        verbose_name_plural = "사장님 한마디"

    def __str__(self):
        return f"{self.place} 사장님 한마디"

    @property
    def has_content(self):
        return any([self.assistance_contact, self.assistance_hours, self.alt_entrance, self.owner_comment])


class VisitWish(models.Model):
    """'가고 싶어요' — 들어가기 어려운 가게에 이용자가 남기는 방문 희망 (사장님에게 수요 신호)"""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="이용자", on_delete=models.CASCADE, related_name="visit_wishes")
    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, related_name="visit_wishes")
    profile = models.ForeignKey(ConditionProfile, verbose_name="이동 조건", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "가고 싶어요"
        verbose_name_plural = "가고 싶어요"
        constraints = [models.UniqueConstraint(fields=["user", "place", "profile"], name="one_wish_per_user_place_profile")]


class PlaceViewStat(models.Model):
    """조건별 조회 수 (일별 집계만, 누가 봤는지는 저장하지 않음 — dev-plan-v2 D8)"""

    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, related_name="view_stats")
    profile = models.ForeignKey(ConditionProfile, verbose_name="이동 조건", on_delete=models.CASCADE, related_name="+")
    date = models.DateField("날짜")
    count = models.PositiveIntegerField("조회 수", default=0)

    class Meta:
        verbose_name = "조회 수"
        verbose_name_plural = "조회 수"
        constraints = [models.UniqueConstraint(fields=["place", "profile", "date"], name="one_stat_per_place_profile_day")]

    @classmethod
    def record(cls, place, profile, day=None):
        stat, _ = cls.objects.get_or_create(place=place, profile=profile, date=day or timezone.localdate())
        cls.objects.filter(pk=stat.pk).update(count=models.F("count") + 1)


class SupportProgram(models.Model):
    """
    경사로 설치 지원사업 안내 (기획 v2 6장). 매년 대상·기간이 바뀌므로 관리자 화면에서 고친다.
    턱없네는 신청을 대신하지 않고 안내·연결만 한다 (6.3).
    """

    region = models.ForeignKey(Region, verbose_name="지역", on_delete=models.CASCADE, related_name="support_programs")
    title = models.CharField("사업명", max_length=100)
    target_desc = models.TextField("지원 대상·내용")
    period = models.CharField("신청 기간", max_length=100, blank=True)
    contact = models.CharField("문의처", max_length=100, blank=True)
    url = models.URLField("안내 링크", blank=True)
    is_active = models.BooleanField("안내 중", default=True)
    order = models.PositiveSmallIntegerField("표시 순서", default=0)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        verbose_name = "지원사업"
        verbose_name_plural = "지원사업"
        ordering = ["order", "-updated_at"]

    def __str__(self):
        return self.title
