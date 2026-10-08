"""
판정 규칙을 코드(if문)가 아닌 데이터로 저장한다 (기획 v2 8장, 12장 3번).

RuleSet(규칙 버전) ─ Rule(이동 조건별 규칙: 결과·우선순위·근거) ─ RuleCondition(조건, 여러 개면 AND)
새 이동 조건 추가 = ConditionProfile 행 + Rule 행 추가. 코드 수정 없음.
판정 방법은 engine.py 참고.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from places.models import Entrance, FieldDefinition, Place


class Outcome(models.TextChoices):
    """판정 4단계. 내부 이름은 중간발표 자료와 맞추기 위해 바꾸지 않는다 (기획 v2). 화면 문구는 constants.py"""

    ACCESSIBLE = "ACCESSIBLE", "가능"
    CONDITIONAL = "CONDITIONAL", "조건부"
    DIFFICULT = "DIFFICULT", "어려움"
    UNKNOWN = "UNKNOWN", "미확인"


class ConditionProfile(models.Model):
    """이동 조건 (휠체어, 유아차 ...)"""

    key = models.SlugField("키", max_length=30, primary_key=True, help_text="예: WHEELCHAIR")
    label = models.CharField("이름", max_length=30)
    order = models.PositiveSmallIntegerField("표시 순서", default=0)
    is_active = models.BooleanField("사용 중", default=True)

    class Meta:
        verbose_name = "이동 조건"
        verbose_name_plural = "이동 조건"
        ordering = ["order", "key"]

    def __str__(self):
        return self.label


class RuleSet(models.Model):
    """규칙 버전. 활성 버전은 하나뿐이고, 판정 결과에 버전을 남긴다"""

    version = models.PositiveIntegerField("버전", unique=True)
    is_active = models.BooleanField("사용 중", default=False)
    note = models.CharField("변경 내용", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "판정 규칙 버전"
        verbose_name_plural = "판정 규칙 버전"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"], condition=models.Q(is_active=True), name="only_one_active_ruleset"
            ),
        ]

    def __str__(self):
        return f"v{self.version}{' (사용 중)' if self.is_active else ''}"

    @classmethod
    def active(cls):
        return cls.objects.filter(is_active=True).first()


class Rule(models.Model):
    class Basis(models.TextChoices):
        LAW = "LAW", "법령"
        APPLIED = "APPLIED", "법령 준용"
        TEAM = "TEAM", "팀 기준"

    class Stage(models.TextChoices):
        """
        규칙을 적용하는 경로 단계. 2층 이상·지하 가게는 "건물 입구 → 층 이동 → 가게 입구"를 모두 지나야 한다.
        이동 조건에 층 이동 규칙이 하나도 없으면 층 이동 단계는 판정에 넣지 않는다 (예전 규칙 버전과 같은 결과)
        """

        ENTRANCE = "ENTRANCE", "출입구"
        FLOOR = "FLOOR", "층 이동 (엘리베이터 등)"

    rule_set = models.ForeignKey(RuleSet, verbose_name="규칙 버전", on_delete=models.CASCADE, related_name="rules")
    profile = models.ForeignKey(ConditionProfile, verbose_name="이동 조건", on_delete=models.CASCADE, related_name="rules")
    stage = models.CharField("적용 단계", max_length=10, choices=Stage.choices, default=Stage.ENTRANCE)
    outcome = models.CharField(
        "결과", max_length=12,
        choices=[(o.value, o.label) for o in Outcome if o != Outcome.UNKNOWN],  # 미확인은 규칙이 아니라 "정보 부족"의 결과
    )
    priority = models.PositiveSmallIntegerField("우선순위", default=100, help_text="작을수록 먼저 확인. 조건이 모두 맞는 첫 규칙의 결과를 씀")
    basis = models.CharField("근거 구분", max_length=10, choices=Basis.choices)
    note = models.CharField("근거 설명", max_length=300, blank=True, help_text="예: 편의증진법 시행규칙 별표 1 — 출입구 턱 2cm 이하")

    class Meta:
        verbose_name = "판정 규칙"
        verbose_name_plural = "판정 규칙"
        ordering = ["rule_set", "profile", "priority", "id"]

    def __str__(self):
        return f"[v{self.rule_set.version} {self.profile}] {self.priority}: {self.get_outcome_display()}"


class RuleCondition(models.Model):
    """
    규칙의 조건 하나. 값 = 필드의 현재 값, 기준 = threshold 또는 (다른 필드 값 × ref_factor).
    예) 입구 단차 ≤ 이동식 경사로 길이 × 0.125  (경사로 1/8 완화 준용, 기획 v2 4.2)
    """

    class Operator(models.TextChoices):
        LT = "LT", "<"
        LTE = "LTE", "≤"
        GT = "GT", ">"
        GTE = "GTE", "≥"
        EQ = "EQ", "="
        NE = "NE", "≠"
        IS_TRUE = "IS_TRUE", "예"
        IS_FALSE = "IS_FALSE", "아니오"

    class IfMissing(models.TextChoices):
        UNKNOWN = "UNKNOWN", "모름으로 처리 (정보가 없으면 미확인)"
        FAIL = "FAIL", "조건 불충족으로 처리 (사장님 선언처럼 없으면 '없음'인 정보)"

    rule = models.ForeignKey(Rule, verbose_name="규칙", on_delete=models.CASCADE, related_name="conditions")
    field = models.ForeignKey(FieldDefinition, verbose_name="필드", on_delete=models.PROTECT, related_name="+")
    operator = models.CharField("비교", max_length=10, choices=Operator.choices)
    threshold = models.DecimalField("기준값", max_digits=8, decimal_places=3, null=True, blank=True)
    threshold_text = models.CharField("기준 글자", max_length=50, blank=True, help_text="선택 필드 비교용. 예: 회전문")
    ref_field = models.ForeignKey(
        FieldDefinition, verbose_name="기준 필드", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    ref_factor = models.DecimalField("기준 필드 배수", max_digits=6, decimal_places=4, default=Decimal("1"))
    if_missing = models.CharField("값이 없을 때", max_length=10, choices=IfMissing.choices, default=IfMissing.UNKNOWN)

    class Meta:
        verbose_name = "규칙 조건"
        verbose_name_plural = "규칙 조건"

    def __str__(self):
        if self.operator in (self.Operator.IS_TRUE, self.Operator.IS_FALSE):
            return f"{self.field.label} = {self.get_operator_display()}"
        if self.ref_field_id:
            target = f"{self.ref_field.label} × {self.ref_factor.normalize():f}"
        else:
            target = self.threshold_text or f"{self.threshold.normalize():f}{self.field.unit}"
        return f"{self.field.label} {self.get_operator_display()} {target}"

    def clean(self):
        op = self.Operator
        if self.operator in (op.IS_TRUE, op.IS_FALSE):
            if self.field.value_type != FieldDefinition.ValueType.BOOL:
                raise ValidationError("예/아니오 비교는 예/아니오 필드에만 쓸 수 있습니다.")
        elif self.threshold is None and not self.threshold_text and not self.ref_field_id:
            raise ValidationError("기준값, 기준 글자, 기준 필드 중 하나가 필요합니다.")


class Judgment(models.Model):
    """
    판정 결과 캐시 (장소 × 이동 조건). 규칙·값이 바뀌면 engine.recompute_place 로 다시 계산한다.
    지도·목록은 이 테이블만 읽어서 빠르다.
    """

    place = models.ForeignKey(Place, verbose_name="장소", on_delete=models.CASCADE, related_name="judgments")
    profile = models.ForeignKey(ConditionProfile, verbose_name="이동 조건", on_delete=models.CASCADE, related_name="+")
    result = models.CharField("결과", max_length=12, choices=Outcome.choices)
    entrance = models.ForeignKey(
        Entrance, verbose_name="판정 근거 출입구", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.CharField("사실 한 줄", max_length=200, blank=True, help_text="예: 입구 단차 30cm · 계단 2칸")
    matched_rule = models.ForeignKey(Rule, verbose_name="적용 규칙", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    rule_version = models.PositiveIntegerField("규칙 버전")
    computed_at = models.DateTimeField("계산 시각", auto_now=True)
    # "개선 완료" 배지 (기획 v2 6.3): 판정이 올라간 날과 그때의 결과. 이후 결과가 이보다 내려가면 배지만 숨김
    improved_at = models.DateTimeField("개선 시각", null=True, blank=True)
    improved_to = models.CharField("개선 후 결과", max_length=12, choices=Outcome.choices, blank=True)

    class Meta:
        verbose_name = "판정 결과"
        verbose_name_plural = "판정 결과"
        constraints = [models.UniqueConstraint(fields=["place", "profile"], name="one_judgment_per_place_profile")]

    def __str__(self):
        return f"{self.place} · {self.profile}: {self.get_result_display()}"

    @property
    def has_improved_badge(self):
        from .constants import IMPROVEMENT_RANK

        if not self.improved_at or not self.improved_to:
            return False
        return IMPROVEMENT_RANK.get(self.result, 0) >= IMPROVEMENT_RANK[self.improved_to]
