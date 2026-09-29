"""
판정 엔진. 기준값은 전부 Rule/RuleCondition 데이터에서 읽는다 (조건별 if문 없음).

판정(장소, 이동 조건)
  1. 경로 만들기
     - 1층 가게: 가게 출입구 하나 = 경로 하나 (정문, 뒷문 … 각각)
     - 1층이 아닌 가게: [건물 공용 출입구 → 가게 출입구(있으면)] 를 하나의 경로로
     - 출입구 정보가 하나도 없으면 → 미확인
  2. 출입구 하나 판정: 우선순위 순서로 규칙을 보고, 조건이 모두 맞는 첫 규칙의 결과.
     맞는 규칙이 없으면 → 어려움. 단, 정보가 없어서 판단 못 한 규칙이 있었으면 → 미확인
  3. 경로 판정: 경로의 출입구 중 하나라도 어려움이면 어려움, 미확인이 있으면 미확인, 아니면 가장 낮은 결과
  4. 장소 판정: 경로 중 가장 좋은 결과 (constants.BEST_ROUTE_ORDER)

값 조회: 조건의 필드가 출입구 필드면 그 출입구 값, 장소 필드면 장소 값, 건물 필드면 건물 값.
값은 검증된(VERIFIED) 최신 값만 쓴다 (reports.selectors.current_values).
overrides 로 가상의 값을 넣어 다시 계산할 수 있다 → "경사로를 놓으면?" 시뮬레이션 (기획 v2 5.2)
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from places.models import FieldDefinition
from reports.selectors import current_values

from .constants import BEST_ROUTE_ORDER, IMPROVEMENT_RANK
from .models import ConditionProfile, Judgment, Outcome, RuleCondition, RuleSet

Scope = FieldDefinition.Scope
Op = RuleCondition.Operator

MAX_FACTS = 2  # 사실 한 줄에 넣을 값 개수


@dataclass
class Subject:
    """판정할 출입구 하나와 그때 참고할 값들 {필드 키: 값}"""

    entrance: object
    values: dict = field(default_factory=dict)          # 출입구 값
    place_values: dict = field(default_factory=dict)    # 장소 값
    building_values: dict = field(default_factory=dict) # 건물 값

    def lookup(self, field_def):
        source = {
            Scope.ENTRANCE: self.values,
            Scope.PLACE: self.place_values,
            Scope.BUILDING: self.building_values,
        }[field_def.scope]
        return source.get(field_def.key)


@dataclass
class Result:
    outcome: str
    entrance: object = None
    rule: object = None
    reason: str = ""
    subject: object = None  # 이 결과를 낸 출입구의 값 (사실 한 줄 만들 때 사용)


# ── 1. 조건·규칙 평가 ─────────────────────────────────────


def evaluate_condition(cond, subject):
    """True / False / None(값이 없어 모름)"""
    value = subject.lookup(cond.field)
    if value is None:
        return False if cond.if_missing == RuleCondition.IfMissing.FAIL else None

    if cond.operator == Op.IS_TRUE:
        return value is True
    if cond.operator == Op.IS_FALSE:
        return value is False

    if cond.ref_field_id:
        ref = subject.lookup(cond.ref_field)
        if ref is None:
            return False if cond.if_missing == RuleCondition.IfMissing.FAIL else None
        target = Decimal(ref) * cond.ref_factor
    elif cond.threshold_text:
        target = cond.threshold_text
    else:
        target = cond.threshold

    if isinstance(target, str):
        value = str(value)
    compare = {
        Op.LT: lambda a, b: a < b,
        Op.LTE: lambda a, b: a <= b,
        Op.GT: lambda a, b: a > b,
        Op.GTE: lambda a, b: a >= b,
        Op.EQ: lambda a, b: a == b,
        Op.NE: lambda a, b: a != b,
    }[cond.operator]
    return compare(value, target)


def evaluate_rule(rule, subject):
    """조건 AND. 하나라도 False면 False, 모르는 조건이 있으면 None"""
    unknown = False
    for cond in rule.conditions.all():
        ok = evaluate_condition(cond, subject)
        if ok is False:
            return False
        if ok is None:
            unknown = True
    return None if unknown else True


def evaluate_subject(rules, subject):
    unknown = False
    for rule in rules:
        matched = evaluate_rule(rule, subject)
        if matched:
            return Result(rule.outcome, subject.entrance, rule, subject=subject)
        if matched is None:
            unknown = True
    return Result(Outcome.UNKNOWN if unknown else Outcome.DIFFICULT, subject.entrance, subject=subject)


# ── 2. 경로 만들기 ────────────────────────────────────────


def _raw(values):
    """{필드 키: AccessibilityValue} → {필드 키: 값}"""
    return {key: v.value for key, v in values.items()}


def build_routes(place, overrides=None):
    """[[Subject, ...], ...] 경로 목록. overrides: {대상 객체: {필드 키: 값}}"""
    overrides = overrides or {}

    def values_of(target):
        vals = _raw(current_values(target)) if target is not None else {}
        vals.update(overrides.get(target, {}))
        return vals

    place_values = values_of(place)
    building = place.building
    building_values = values_of(building) if building else {}

    def subject(entrance):
        return Subject(entrance, values_of(entrance), place_values, building_values)

    place_entrances = list(place.entrances.all())
    if place.floor == 1 or not building:
        return [[subject(e)] for e in place_entrances]

    building_entrances = list(building.entrances.all())
    if not building_entrances:
        return [[subject(e)] for e in place_entrances]
    inner = place_entrances or [None]
    return [
        [subject(b)] + ([subject(p)] if p is not None else [])
        for b in building_entrances
        for p in inner
    ]


# ── 3. 경로·장소 판정 ─────────────────────────────────────


def combine_route(results):
    """경로는 모든 출입구를 지나야 하므로: 어려움이 하나라도 있으면 어려움, 아니면 가장 나쁜 결과"""
    for r in results:
        if r.outcome == Outcome.DIFFICULT:
            return r
    # BEST_ROUTE_ORDER에서 뒤에 있을수록 나쁨 (가능 < 조건부 < 미확인)
    return max(results, key=lambda r: BEST_ROUTE_ORDER.index(r.outcome))


def _fmt(value):
    return f"{Decimal(value).normalize():f}"  # 30.00 → 30


def facts_line(result, rules, all_rules):
    """
    사실 한 줄 (기획 v2 3.1: 어려움 옆에 항상 사실 한 줄. 예: 입구 단차 30cm · 계단 수 2칸)
      1. 이 이동 조건의 기준에 걸린 출입구 숫자 값
      2. 자리가 남으면, 다른 규칙에서 쓰는 출입구 숫자 값 중 0보다 큰 것 (계단 수 등)
      기준을 통과한 값(예: 충분한 문 폭)은 이유가 아니므로 넣지 않는다
    """
    subject = result.subject
    if subject is None:
        return ""

    def numeric_entrance_fields(rule_list):
        for rule in rule_list:
            for cond in rule.conditions.all():
                if cond.field.scope == Scope.ENTRANCE and cond.field.value_type == FieldDefinition.ValueType.NUMBER:
                    yield cond

    failed, passed = [], set()
    for cond in numeric_entrance_fields(rules):
        ok = evaluate_condition(cond, subject)
        if ok is False and cond.field not in failed:
            failed.append(cond.field)
        elif ok is True:
            passed.add(cond.field)

    extra = []
    for cond in numeric_entrance_fields(all_rules):
        f = cond.field
        if f in failed or f in passed or f in extra:
            continue
        value = subject.values.get(f.key)
        if value is not None and Decimal(value) > 0:
            extra.append(f)

    fields = sorted(failed, key=lambda f: f.order) + sorted(extra, key=lambda f: f.order)
    parts = [f"{f.label} {_fmt(subject.values[f.key])}{f.unit}" for f in fields if f.key in subject.values]
    return " · ".join(parts[:MAX_FACTS])


def judge(place, profile, rule_set=None, overrides=None):
    """장소 하나 × 이동 조건 하나 → Result (저장하지 않음)"""
    rule_set = rule_set or RuleSet.active()
    if rule_set is None:
        return Result(Outcome.UNKNOWN)
    all_rules = list(
        rule_set.rules.prefetch_related("conditions__field", "conditions__ref_field").order_by("priority", "id")
    )
    rules = [r for r in all_rules if r.profile_id == profile.pk]
    routes = build_routes(place, overrides)
    if not routes:
        return Result(Outcome.UNKNOWN)

    route_results = [combine_route([evaluate_subject(rules, s) for s in route]) for route in routes]
    best = min(route_results, key=lambda r: BEST_ROUTE_ORDER.index(r.outcome))
    if best.outcome in (Outcome.DIFFICULT, Outcome.CONDITIONAL):
        best.reason = facts_line(best, rules, all_rules)
    return best


# ── 4. 저장 ───────────────────────────────────────────────


@transaction.atomic
def recompute_place(place, rule_set=None):
    """장소의 모든 이동 조건 판정을 다시 계산해서 저장. 개선(판정 상승) 시각도 기록"""
    rule_set = rule_set or RuleSet.active()
    if rule_set is None:
        return []
    saved = []
    for profile in ConditionProfile.objects.filter(is_active=True):
        result = judge(place, profile, rule_set)
        judgment = Judgment.objects.filter(place=place, profile=profile).first()
        previous = judgment.result if judgment else None
        judgment = judgment or Judgment(place=place, profile=profile)

        judgment.result = result.outcome
        judgment.entrance = result.entrance
        judgment.reason = result.reason
        judgment.matched_rule = result.rule
        judgment.rule_version = rule_set.version
        if _is_improvement(previous, result.outcome):
            judgment.improved_at = timezone.now()
            judgment.improved_to = result.outcome
        judgment.save()
        saved.append(judgment)
    return saved


def _is_improvement(previous, current):
    """미확인이 아닌 결과에서 한 단계 이상 올라갔을 때만 개선으로 본다"""
    if previous not in IMPROVEMENT_RANK or current not in IMPROVEMENT_RANK:
        return False
    return IMPROVEMENT_RANK[current] > IMPROVEMENT_RANK[previous]
