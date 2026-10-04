"""
접근성 값과 그 출처.

Report(제보 묶음) 1건 = 사진 1장 + 필드 값 여러 개.
팀 답사·이용자 제보·사장님 선언·AI 판별 모두 같은 구조로 들어오고, source 로 구분한다 (dev-plan-v2 D4, D7).
아직 등록 안 된 장소는 대상 없이 "새 장소 제안"(이름·위치)으로 제보하고, 운영자가 승인할 때 장소를 만든다.
판정에는 status=VERIFIED 인 값만 쓴다. PENDING 은 "확인 중"으로만 보여준다 (기획 v2 OP-6).
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from places.models import AccessFacility, Building, Entrance, FieldDefinition, Place
from places.validation import parse_boolean, validate_number

# 주민 '사진 수정 요청' 표시: 값 없이 사진(선택)과 이유만 담긴 주민 제보의 설명 앞에 붙인다.
# 운영자만 처리한다 (judgments.services.is_photo_request → required_confirmations 가 None)
PHOTO_FIX_PREFIX = "[사진 수정 요청]"


class Report(models.Model):
    class Source(models.TextChoices):
        TEAM_SURVEY = "TEAM_SURVEY", "팀 답사"
        USER_REPORT = "USER_REPORT", "이용자 제보"
        OWNER = "OWNER", "사장님·건물주"
        AI = "AI", "AI 판별"
        PUBLIC_DATA = "PUBLIC_DATA", "공공데이터"  # 장애인편의시설 현황 API (places/public_data.py)

    class Status(models.TextChoices):
        PENDING = "PENDING", "확인 중"
        VERIFIED = "VERIFIED", "반영됨"
        REJECTED = "REJECTED", "반려"

    # 대상: 장소·건물·출입구·접근 시설 중 정확히 하나 (새 장소 제안은 예외).
    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    entrance = models.ForeignKey(
        Entrance, verbose_name="출입구", on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    facility = models.ForeignKey(AccessFacility, verbose_name="접근 시설", on_delete=models.CASCADE,
                                 null=True, blank=True, related_name="reports")
    facility_kind = models.CharField("제안 시설 종류", max_length=20, blank=True,
                                     choices=[("ENTRANCE", "출입구")] + list(AccessFacility.Kind.choices))
    facility_name = models.CharField("제안 시설 이름", max_length=50, blank=True)

    # 새 장소 제안: 대상이 없을 때만 사용 (운영자가 승인하면서 장소를 만든다)
    suggested_name = models.CharField("새 장소 이름", max_length=100, blank=True)
    suggested_category = models.CharField("제안 업종", max_length=20, choices=Place.Category.choices, blank=True)
    suggested_address = models.CharField("제안 주소", max_length=200, blank=True)
    suggested_floor = models.SmallIntegerField("제안 층", null=True, blank=True)
    suggested_phone = models.CharField("제안 전화번호", max_length=20, blank=True)
    location_text = models.CharField("위치 설명", max_length=200, blank=True, help_text="예: 월계역 2번 출구 앞 건물 1층")
    lat = models.DecimalField("제보 위치 위도", max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField("제보 위치 경도", max_digits=9, decimal_places=6, null=True, blank=True)

    source = models.CharField("출처", max_length=20, choices=Source.choices)
    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.PENDING)
    photo = models.ImageField("사진", upload_to="reports/%Y/%m/", blank=True)
    note = models.CharField("설명", max_length=500, blank=True)
    profiles = models.JSONField("이동 조건", default=list, blank=True, help_text='제보자가 고른 이동 조건 키 목록. 예: ["WHEELCHAIR"]')
    # 실제로 현장을 확인한 시각. 운영자가 예전 답사 기록을 나중에 입력할 수 있어서 작성 시각과 따로 둔다.
    # "지금 쓸 값"은 이 시각이 가장 최근인 제보로 정한다 (reports/selectors.py)
    observed_at = models.DateTimeField("확인 시각", default=timezone.now)
    # 제출한 폼에 붙어 있던 AI 활용 안내 버전 (AI 명세 v1.3 7.1). 안내를 '봤다'·'동의했다'는 뜻은 아님.
    # 빈 값 = 안내 없이 제출 → AI로 보내지 않음. db_default: 이전 버전 코드로 롤백해도 제보 저장이 깨지지 않게
    ai_notice_version = models.CharField("AI 안내 버전", max_length=40, blank=True, default="", db_default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="작성자", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reports",
    )
    created_at = models.DateTimeField("작성일", auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="처리자", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_reports",
    )
    reviewed_at = models.DateTimeField("처리일", null=True, blank=True)
    reject_reason = models.CharField("반려 사유", max_length=200, blank=True)
    review_note = models.CharField("검토 의견", max_length=300, blank=True, help_text="충돌 항목 처리 방향 등 (처리 기록)")

    class Meta:
        verbose_name = "제보"
        verbose_name_plural = "제보"
        ordering = ["-created_at"]
        constraints = [
            # 대상(장소·건물·출입구)은 정확히 하나. 대상이 없으면 새 장소 이름이 있어야 함
            models.CheckConstraint(
                condition=(
                    models.Q(place__isnull=False, building__isnull=True, entrance__isnull=True, facility__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=False, entrance__isnull=True, facility__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=True, entrance__isnull=False, facility__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=True, entrance__isnull=True, facility__isnull=False)
                    | (
                        models.Q(place__isnull=True, building__isnull=True, entrance__isnull=True)
                        & models.Q(facility__isnull=True)
                        & ~models.Q(suggested_name="")
                    )
                ),
                name="report_has_one_target_or_new_place",
            ),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.target} ({self.get_source_display()})"

    def clean(self):
        if self.facility_id and self.facility_kind not in ("", self.facility.kind):
            raise ValidationError({"facility_kind": "연결된 시설과 제안 종류가 다릅니다."})
        if self.entrance_id and self.facility_kind not in ("", "ENTRANCE"):
            raise ValidationError({"facility_kind": "출입구에는 다른 시설 종류를 연결할 수 없습니다."})

    def save(self, *args, **kwargs):
        # 새로 올린 사진은 저장 전에 EXIF(촬영 위치 GPS·기기 정보)를 지우고 크기를 줄인다 (core/images.py).
        # 주민 제보·사장님 요청·관리자 화면 어디서 올려도 여기를 거친다. 이미 저장된 사진은 건드리지 않음
        if self.photo and not self.photo._committed:
            from core.images import normalize_photo

            self.photo = normalize_photo(self.photo.file, name=self.photo.name)
        super().save(*args, **kwargs)

    @property
    def target(self):
        return self.place or self.building or self.entrance or self.facility

    @property
    def is_facility_proposal(self):
        return bool(self.facility_kind and not self.entrance_id and not self.facility_id)

    @property
    def is_facility_report(self):
        return bool(self.facility_id or self.is_facility_proposal)

    @property
    def is_new_place(self):
        return self.target is None

    @property
    def target_label(self):
        """화면 표시용 대상 이름"""
        if self.is_new_place:
            return f"새 장소: {self.suggested_name}"
        if self.is_facility_proposal:
            return f"{self.target} · {self.facility_name or self.get_facility_kind_display()} (새 시설 제안)"
        return str(self.target)

    @property
    def target_place(self):
        """이 제보가 속한 장소 (출입구 제보면 그 출입구의 장소). 건물·새 장소 제보는 None"""
        if self.place_id:
            return self.place
        if self.entrance_id and self.entrance.place_id:
            return self.entrance.place
        if self.facility_id:
            return self.facility.place
        return None

    @property
    def target_scope(self):
        """이 제보에 들어갈 수 있는 필드의 대상(FieldDefinition.Scope). 새 장소 제안은 입구 정보를 받는다"""
        if self.facility_id or self.facility_kind in AccessFacility.Kind.values:
            return FieldDefinition.Scope.FACILITY
        if self.facility_kind == "ENTRANCE" or self.entrance_id or self.is_new_place:
            return FieldDefinition.Scope.ENTRANCE
        if self.building_id:
            return FieldDefinition.Scope.BUILDING
        return FieldDefinition.Scope.PLACE


class AccessibilityValue(models.Model):
    """
    필드 값 하나. 값 종류(FieldDefinition.value_type)에 맞는 칸 하나만 채운다 (dev-plan-v2 D2).
    판정 엔진이 숫자로 비교할 수 있도록 숫자는 value_number(Decimal)에 저장한다.
    """

    report = models.ForeignKey(Report, verbose_name="제보", on_delete=models.CASCADE, related_name="values")
    field = models.ForeignKey(FieldDefinition, verbose_name="필드", on_delete=models.PROTECT, related_name="values")
    value_number = models.DecimalField("숫자 값", max_digits=8, decimal_places=2, null=True, blank=True)
    value_bool = models.BooleanField("예/아니오 값", null=True, blank=True)
    value_text = models.CharField("글·선택 값", max_length=200, blank=True)

    class Meta:
        verbose_name = "접근성 값"
        verbose_name_plural = "접근성 값"
        constraints = [
            models.UniqueConstraint(fields=["report", "field"], name="one_value_per_field_per_report"),
        ]

    def __str__(self):
        unit = f" {self.field.unit}" if self.field.unit else ""
        return f"{self.field.label}: {self.display_value}{unit}"

    @property
    def value(self):
        vt = FieldDefinition.ValueType
        if self.field.value_type == vt.NUMBER:
            return self.value_number
        if self.field.value_type == vt.BOOL:
            return self.value_bool
        return self.value_text or None

    @property
    def display_value(self):
        v = self.value
        if isinstance(v, bool):
            return "있음" if v else "없음"
        if isinstance(v, Decimal):
            return f"{v.normalize():f}"  # 30.00 → 30
        return v if v is not None else "-"

    def set_value(self, raw):
        """폼·API에서 받은 값을 필드 종류에 맞는 칸에 넣는다"""
        vt = FieldDefinition.ValueType
        self.value_number, self.value_bool, self.value_text = None, None, ""
        if self.field.value_type == vt.NUMBER:
            self.value_number = validate_number(self.field_id, raw, self.field.label)
        elif self.field.value_type == vt.BOOL:
            self.value_bool = parse_boolean(raw)
        else:
            self.value_text = str(raw).strip()

    def clean(self):
        vt = FieldDefinition.ValueType
        filled = {
            vt.NUMBER: self.value_number is not None,
            vt.BOOL: self.value_bool is not None,
            vt.CHOICE: bool(self.value_text),
            vt.TEXT: bool(self.value_text),
        }
        if not filled[self.field.value_type]:
            raise ValidationError(f"{self.field.label}: 값 종류({self.field.get_value_type_display()})에 맞는 값이 없습니다.")
        if self.field.value_type == vt.NUMBER:
            validate_number(self.field_id, self.value_number, self.field.label)
        if self.field.value_type == vt.BOOL:
            self.value_bool = parse_boolean(self.value_bool)
        if self.field.value_type == vt.CHOICE and self.value_text not in self.field.choices:
            raise ValidationError(f"{self.field.label}: 선택지({', '.join(self.field.choices)}) 중 하나여야 합니다.")
        if self.report_id and self.field.scope != self.report.target_scope:
            raise ValidationError(
                f"{self.field.label}은(는) {self.field.get_scope_display()} 필드라서 이 제보 대상에 넣을 수 없습니다."
            )
        if self.report_id and self.field.scope == FieldDefinition.Scope.FACILITY:
            from places.facilities import KIND_FIELDS

            kind = self.report.facility.kind if self.report.facility_id else self.report.facility_kind
            if self.field_id not in KIND_FIELDS.get(kind, ()):
                raise ValidationError("선택한 시설 종류에서 사용할 수 없는 관측 항목입니다.")

    def save(self, *args, **kwargs):
        # Form을 통하지 않는 create/save도 검증한다. unique 제약은 기존처럼 DB에서 보장한다.
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)


class ReportConfirmation(models.Model):
    """다른 이용자의 "맞아요" 확인. 반영 기준(확인 1명/2명)은 기획 v2 7장 — 제보 흐름에서 처리"""

    report = models.ForeignKey(Report, verbose_name="제보", on_delete=models.CASCADE, related_name="confirmations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="확인한 사람", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "제보 확인"
        verbose_name_plural = "제보 확인"
        constraints = [
            models.UniqueConstraint(fields=["report", "user"], name="one_confirmation_per_user"),
        ]

    def clean(self):
        if self.report.created_by_id and self.report.created_by_id == self.user_id:
            raise ValidationError("본인 제보는 확인할 수 없습니다.")


class Reconfirmation(models.Model):
    """
    "지금도 맞아요" — 주민이 가게에 가 보고 공개된 정보가 여전히 맞다고 확인한 기록.
    판정·값에는 쓰지 않고 '최근 확인일'·신뢰도 표시에만 쓴다.
    값을 복사해 새 제보로 만들지 않는 이유: 복사본이 더 최신이 되면, 확인 중이던 하향 제보가 나중에 승인돼도
    반영되지 않는다 (reports.selectors.current_values는 가장 최근 확인한 값을 씀). 같은 사람·같은 가게는 하루 한 번.
    """

    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, related_name="reconfirmations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="확인한 사람", on_delete=models.CASCADE,
                             related_name="reconfirmations")
    created_at = models.DateTimeField("확인 시각", default=timezone.now)

    class Meta:
        verbose_name = "지금도 맞아요"
        verbose_name_plural = "지금도 맞아요"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["place", "-created_at"], name="reconfirm_place_recent")]

    def __str__(self):
        return f"{self.place} · {self.user} ({self.created_at:%Y-%m-%d})"


class AIAnalysis(models.Model):
    """
    운영자 AI 검토 보조 기록 (AI 명세 v1.2 A안, reports/ai.py).
    제보 사진·설명에서 뽑은 출입구 항목 '후보'와, 운영자가 그중 골라 제보에 저장한 기록을 남긴다.
    분석만으로는 제보·값·판정을 바꾸지 않는다. 승인은 기존 운영자 승인 흐름만 한다.

    저장하지 않고 계산하는 값 (레포 규칙: 파생값은 계산):
      - 운영자 승인 전용 여부: 선택 기록(selection_history)이 있는 분석이 하나라도 있는지 (reports.ai.staff_review_only)
      - 입력 변경 여부: input_snapshot ↔ 지금 제보 값
      - 60초 넘게 PROCESSING인 기록 = 실패 (작업자가 강제 종료된 경우)
    """

    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "분석 중"
        SUCCEEDED = "SUCCEEDED", "완료"
        FAILED = "FAILED", "실패"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # 폼·주소에 넣어도 순서 추측 불가
    # 제보를 지워도 행은 남겨 오늘 호출 횟수에 계속 센다. 내용은 지울 때 비운다 (reports.ai.clear_on_report_delete)
    report = models.ForeignKey(Report, verbose_name="제보", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="ai_analyses")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="요청한 운영자", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="+")
    status = models.CharField("상태", max_length=12, choices=Status.choices, default=Status.PROCESSING)
    created_at = models.DateTimeField("요청 시각", auto_now_add=True)  # 일일 한도는 이 시각으로 센다
    completed_at = models.DateTimeField("완료 시각", null=True, blank=True)

    input_snapshot = models.JSONField("분석 시점 입력", default=dict)          # 값이 바뀌었는지 비교용 (외부로 보내지 않음)
    field_definition_snapshot = models.JSONField("분석 시점 항목 정의", default=dict)
    result = models.JSONField("검증한 결과", null=True, blank=True)
    error_code = models.CharField("오류 코드", max_length=40, blank=True)
    error_message = models.CharField("오류 안내", max_length=200, blank=True)  # 정리한 안내만 (제공자 오류 원문 저장 안 함)

    model_id = models.CharField("모델", max_length=100, blank=True)
    prompt_version = models.CharField("지시문 버전", max_length=50, blank=True)
    schema_version = models.CharField("출력 형식 버전", max_length=50, blank=True)
    provider_response_id = models.CharField("OpenAI 응답 번호", max_length=100, blank=True)
    usage = models.JSONField("토큰 사용량", null=True, blank=True)
    # [{"by": 운영자 id, "by_name", "at", "changes": [{"key", "before", "after"}]}] — 분석 하나에 한 번만 저장
    selection_history = models.JSONField("운영자 선택 기록", default=list, blank=True)

    class Meta:
        verbose_name = "AI 검토 보조 기록"
        verbose_name_plural = "AI 검토 보조 기록"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"], name="ai_analysis_created")]

    def __str__(self):
        target = f"{self.report_id}번 제보" if self.report_id else "삭제된 제보"
        return f"{target} · {self.get_status_display()} ({self.created_at:%Y-%m-%d %H:%M})"
