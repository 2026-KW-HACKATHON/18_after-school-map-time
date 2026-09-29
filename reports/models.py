"""
접근성 값과 그 출처.

Report(제보 묶음) 1건 = 사진 1장 + 필드 값 여러 개.
팀 답사·이용자 제보·사장님 선언·AI 판별 모두 같은 구조로 들어오고, source 로 구분한다 (dev-plan-v2 D4, D7).
판정에는 status=VERIFIED 인 값만 쓴다. PENDING 은 "확인 중"으로만 보여준다 (기획 v2 OP-6).
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from places.models import Building, Entrance, FieldDefinition, Place


class Report(models.Model):
    class Source(models.TextChoices):
        TEAM_SURVEY = "TEAM_SURVEY", "팀 답사"
        USER_REPORT = "USER_REPORT", "이용자 제보"
        OWNER = "OWNER", "사장님·건물주"
        AI = "AI", "AI 판별"

    class Status(models.TextChoices):
        PENDING = "PENDING", "확인 중"
        VERIFIED = "VERIFIED", "반영됨"
        REJECTED = "REJECTED", "반려"

    # 대상: 장소·건물·출입구 중 정확히 하나 (dev-plan-v2 D1)
    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    entrance = models.ForeignKey(
        Entrance, verbose_name="출입구", on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )

    source = models.CharField("출처", max_length=20, choices=Source.choices)
    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.PENDING)
    photo = models.ImageField("사진", upload_to="reports/%Y/%m/", blank=True)
    note = models.CharField("메모", max_length=200, blank=True)

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

    class Meta:
        verbose_name = "제보"
        verbose_name_plural = "제보"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(place__isnull=False, building__isnull=True, entrance__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=False, entrance__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=True, entrance__isnull=False)
                ),
                name="report_has_exactly_one_target",
            ),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.target} ({self.get_source_display()})"

    @property
    def target(self):
        return self.place or self.building or self.entrance

    @property
    def target_scope(self):
        """이 제보에 들어갈 수 있는 필드의 대상(FieldDefinition.Scope)"""
        if self.entrance_id:
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
            try:
                self.value_number = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                raise ValidationError({"value": f"{self.field.label}: 숫자를 입력하세요."})
        elif self.field.value_type == vt.BOOL:
            if isinstance(raw, str):
                raw = raw.strip().lower() in ("true", "1", "yes", "y", "있음", "예")
            self.value_bool = bool(raw)
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
        if self.field.value_type == vt.NUMBER and self.value_number < 0:
            raise ValidationError(f"{self.field.label}: 0 이상이어야 합니다.")
        if self.field.value_type == vt.CHOICE and self.value_text not in self.field.choices:
            raise ValidationError(f"{self.field.label}: 선택지({', '.join(self.field.choices)}) 중 하나여야 합니다.")
        if self.report_id and self.field.scope != self.report.target_scope:
            raise ValidationError(
                f"{self.field.label}은(는) {self.field.get_scope_display()} 필드라서 이 제보 대상에 넣을 수 없습니다."
            )


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
