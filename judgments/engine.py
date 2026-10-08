"""
판정 엔진. 기준값은 전부 Rule/RuleCondition 데이터에서 읽는다 (조건별 if문 없음).

판정(장소, 이동 조건)
  1. 경로 만들기
     - 1층 가게: 가게 출입구 하나 = 경로 하나 (정문, 뒷문 … 각각)
     - 1층이 아닌 가게: [건물 공용 출입구 → 층 이동 → 가게 출입구(있으면)] 를 하나의 경로로
       층 이동 = 건물 값(엘리베이터 등)으로 판정하는 단계. 이 이동 조건에 층 이동 규칙(Rule.stage=FLOOR)이
       하나도 없으면 넣지 않는다 (예전 규칙 버전과 같은 결과)
     - 출입구 정보가 하나도 없으면 → 미확인
  2. 단계 하나 판정: 그 단계(출입구/층 이동)의 규칙을 우선순위 순서로 보고, 조건이 모두 맞는 첫 규칙의 결과.
     맞는 규칙이 없으면 → 어려움. 단, 정보가 없어서 판단 못 한 규칙이 있었으면 → 미확인
  3. 경로 판정: 경로의 단계 중 하나라도 어려움이면 어려움, 미확인이 있으면 미확인, 아니면 가장 낮은 결과
  4. 장소 판정: 경로 중 가장 좋은 결과 (constants.BEST_ROUTE_ORDER)

값 조회: 조건의 필드가 출입구 필드면 그 출입구 값, 장소 필드면 장소 값, 건물 필드면 건물 값.
값은 검증된(VERIFIED) 최신 값만 쓴다 (reports.selectors.current_values).
overrides 로 가상의 값을 넣어 다시 계산할 수 있다 → "경사로를 놓으면?" 시뮬레이션 (기획 v2 5.2)
"""

from dataclasses import dataclass, field, replace
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from places.models import FieldDefinition
from reports.selectors import current_values

from .constants import BEST_ROUTE_ORDER, IMPROVEMENT_RANK
from .models import ConditionProfile, Judgment, Outcome, Rule, RuleCondition, RuleSet
from .signals import place_improved

Scope = FieldDefinition.Scope
Op = RuleCondition.Operator

MAX_FACTS = 2  # 사실 한 줄에 넣을 값 개수


@dataclass
class Subject:
    """판정할 경로 단계 하나(출입구 또는 층 이동)와 그때 참고할 값들 {필드 키: 값}"""

    entrance: object
    values: dict = field(default_factory=dict)          # 출입구 값
    place_values: dict = field(default_factory=dict)    # 장소 값
    building_values: dict = field(default_factory=dict) # 건물 값
    floor: int | None = None                            # 층 이동 단계면 가게 층 (출입구 단계는 None)

    @property
    def is_floor(self):
        return self.floor is not None

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


def evaluate_condition(cond, subject, criteria=None):
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

    # 장소 관측값(overrides 시뮬레이션)과 사용자 기준을 분리한다. Rule/DB는 변경하지 않는다.
    criteria = criteria or {}
    if not cond.ref_field_id:
        key = {"step_height_cm": "max_step_height_cm", "door_width_cm": "min_door_width_cm"}.get(cond.field_id)
        if key in criteria and cond.operator in (Op.LTE, Op.GTE):
            target = Decimal(criteria[key])
        if cond.field_id == "step_count" and "can_use_stairs" in criteria and cond.operator == Op.LTE:
            return True if criteria["can_use_stairs"] else Decimal(value) == 0

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


def evaluate_rule(rule, subject, criteria=None):
    """조건 AND. 하나라도 False면 False, 모르는 조건이 있으면 None"""
    unknown = False
    for cond in rule.conditions.all():
        ok = evaluate_condition(cond, subject, criteria)
        if ok is False:
            return False
        if ok is None:
            unknown = True
    return None if unknown else True


def evaluate_subject(rules, subject, criteria=None):
    unknown = False
    for rule in rules:
        matched = evaluate_rule(rule, subject, criteria)
        if matched:
            return Result(rule.outcome, subject.entrance, rule, subject=subject)
        if matched is None:
            unknown = True
    return Result(Outcome.UNKNOWN if unknown else Outcome.DIFFICULT, subject.entrance, subject=subject)


# ── 2. 경로 만들기 ────────────────────────────────────────


def _raw(values):
    """{필드 키: AccessibilityValue} → {필드 키: 값}"""
    return {key: v.value for key, v in values.items()}


def build_routes(place, overrides=None, with_floor=False):
    """
    [[Subject, ...], ...] 경로 목록. overrides: {대상 객체: {필드 키: 값}}
    with_floor: 1층이 아닌 가게에 층 이동 단계를 넣을지 (층 이동 규칙이 있는 이동 조건만)
    """
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

    # 층 이동: 건물 값(엘리베이터)으로 판정. 건물이 등록 안 됐으면 값이 없어 미확인
    floor_step = (
        [Subject(None, {}, place_values, building_values, floor=place.floor)]
        if with_floor and place.floor != 1 else []
    )
    place_entrances = list(place.entrances.all())
    if place.floor == 1 or not building:
        return [floor_step + [subject(e)] for e in place_entrances]

    building_entrances = list(building.entrances.all())
    if not building_entrances:
        return [floor_step + [subject(e)] for e in place_entrances]
    inner = place_entrances or [None]
    return [
        [subject(b)] + floor_step + ([subject(p)] if p is not None else [])
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


def floor_label(floor):
    return f"지하 {-floor}층" if floor < 0 else f"{floor}층"


def floor_facts(subject, rules):
    """층 이동 단계의 사실 한 줄. 예: 2층 · 엘리베이터 없음 (기준에 걸린 예/아니오 값만)"""
    parts = [floor_label(subject.floor)]
    for rule in rules:
        for cond in rule.conditions.all():
            value = subject.lookup(cond.field)
            if value is None or cond.field.value_type != FieldDefinition.ValueType.BOOL:
                continue
            text = f"{cond.field.label} {'있음' if value else '없음'}"
            if text not in parts and evaluate_condition(cond, subject) is False:
                parts.append(text)
    return " · ".join(parts[:MAX_FACTS])


def facts_line(result, rules, all_rules, criteria=None):
    """
    사실 한 줄 (기획 v2 3.1: 어려움 옆에 항상 사실 한 줄. 예: 입구 단차 30cm · 계단 수 2칸)
      1. 이 이동 조건의 기준에 걸린 출입구 숫자 값
      2. 자리가 남으면, 다른 이동 조건의 기준에 걸린 출입구 숫자 값 (계단 수 등)
      기준을 통과한 값(예: 충분한 문 폭)은 이유가 아니므로 넣지 않는다
    층 이동 단계가 결과를 냈으면 "2층 · 엘리베이터 없음"
    """
    subject = result.subject
    if subject is None:
        return ""
    if subject.is_floor:
        return floor_facts(subject, [r for r in rules if r.stage == Rule.Stage.FLOOR])
    rules = [r for r in rules if r.stage == Rule.Stage.ENTRANCE]
    all_rules = [r for r in all_rules if r.stage == Rule.Stage.ENTRANCE]

    def numeric_entrance_fields(rule_list):
        for rule in rule_list:
            for cond in rule.conditions.all():
                if cond.field.scope == Scope.ENTRANCE and cond.field.value_type == FieldDefinition.ValueType.NUMBER:
                    yield cond

    failed, passed = [], set()
    for cond in numeric_entrance_fields(rules):
        ok = evaluate_condition(cond, subject, criteria)
        if ok is False and cond.field not in failed:
            failed.append(cond.field)
        elif ok is True:
            passed.add(cond.field)

    # 덧붙이는 값도 "어떤 이동 조건에서든 기준에 걸린 값"만 (예: 계단 수). 문 폭처럼 걸린 적 없는 값은 이유가 아님
    extra = []
    for cond in numeric_entrance_fields(all_rules):
        f = cond.field
        if f in failed or f in passed or f in extra:
            continue
        if evaluate_condition(cond, subject, criteria) is False:
            extra.append(f)

    fields = sorted(failed, key=lambda f: f.order) + sorted(extra, key=lambda f: f.order)
    parts = [f"{f.label} {_fmt(subject.values[f.key])}{f.unit}" for f in fields if f.key in subject.values]
    return " · ".join(parts[:MAX_FACTS])


def judge(place, profile, rule_set=None, overrides=None):
    """장소 하나 × 이동 조건 하나 → Result (저장하지 않음)"""
    return judge_profiles(place, [(profile, {})], rule_set=rule_set, overrides=overrides)


def load_rules(rule_set):
    """규칙 버전의 규칙 전체 (조건·필드까지). 여러 장소를 판정할 땐 한 번만 읽어 judge_profiles에 넘긴다"""
    return list(
        rule_set.rules.prefetch_related("conditions__field", "conditions__ref_field").order_by("priority", "id")
    )


def judge_profiles(place, requirements, rule_set=None, overrides=None, all_rules=None):
    """개인별 규칙을 동일 경로에 적용한다. 서로 다른 사람의 가장 좋은 입구를 섞지 않는다."""
    rule_set = rule_set or RuleSet.active()
    if rule_set is None or not requirements:
        return Result(Outcome.UNKNOWN)
    if all_rules is None:
        all_rules = load_rules(rule_set)
    rule_groups = [[r for r in all_rules if r.profile_id == profile.pk] for profile, _ in requirements]
    with_floor = any(r.stage == Rule.Stage.FLOOR for rules in rule_groups for r in rules) or any(
        c.get("needs_elevator") is True or c.get("can_use_stairs") is False for _, c in requirements)
    routes = build_routes(place, overrides, with_floor=with_floor)
    if not routes:
        return Result(Outcome.UNKNOWN)

    from .mobility_checks import elevator_fact, extra_requirements

    def evaluate(subject, rules, criteria):
        stage = Rule.Stage.FLOOR if subject.is_floor else Rule.Stage.ENTRANCE
        if subject.is_floor and (criteria.get("needs_elevator") is True or criteria.get("can_use_stairs") is False) and elevator_fact(place, subject) is True:
            # 연결 층까지 검증된 E/V 정보를 기존 층 이동 Rule에 공급한다. 건물 관측값은 덮어쓰지 않는다.
            subject = replace(subject, building_values={**subject.building_values, "elevator": True})
        stage_rules = [r for r in rules if r.stage == stage]
        result = (Result(Outcome.ACCESSIBLE, subject=subject) if subject.is_floor and not stage_rules
                  else evaluate_subject(stage_rules, subject, criteria))
        extra = extra_requirements(place, subject, criteria, result, rules)
        if extra and (result.outcome != Outcome.DIFFICULT or extra[0] == Outcome.ACCESSIBLE):
            result = Result(extra[0], subject.entrance, reason=extra[1], subject=subject)
        if result.outcome in (Outcome.DIFFICULT, Outcome.CONDITIONAL) and not result.reason:
            result.reason = facts_line(result, rules, all_rules, criteria)
        return result

    route_results = [combine_route([
        evaluate(subject, rules, criteria)
        for subject in route
        for (_, criteria), rules in zip(requirements, rule_groups)
    ]) for route in routes]
    best = min(route_results, key=lambda r: BEST_ROUTE_ORDER.index(r.outcome))
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
        improved = _is_improvement(previous, result.outcome)
        if improved:
            judgment.improved_at = timezone.now()
            judgment.improved_to = result.outcome
        judgment.save()
        if improved:
            place_improved.send(sender=Judgment, judgment=judgment)  # 가고 싶어요 누른 주민 알림 (owners)
        saved.append(judgment)
    return saved


def _is_improvement(previous, current):
    """미확인이 아닌 결과에서 한 단계 이상 올라갔을 때만 개선으로 본다"""
    if previous not in IMPROVEMENT_RANK or current not in IMPROVEMENT_RANK:
        return False
    return IMPROVEMENT_RANK[current] > IMPROVEMENT_RANK[previous]
