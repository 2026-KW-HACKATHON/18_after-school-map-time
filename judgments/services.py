"""
제보가 판정에 미칠 영향 계산 (기획 v2 7장 — 판정이 내려가는 정보는 더 엄격하게 검증).

판정 엔진에 제보 값을 가상으로 넣어 다시 계산하고(engine.judge의 overrides), 지금 판정과 비교한다.
"""

from dataclasses import dataclass

from .constants import IMPROVEMENT_RANK
from .engine import judge
from .models import ConditionProfile, Outcome, RuleSet
from .receivers import affected_places

DOWN, UP, SAME = "DOWN", "UP", "SAME"

# 반영에 필요한 주민 확인 수 (운영자 승인은 언제나 가능)
REQUIRED_CONFIRMATIONS = {DOWN: 2, UP: 1, SAME: 1}

# 사장님 제보 (기획 v2 4.2·4.3)
#  - 도움 제공·이동식 경사로 '선언'만 담긴 제보: 사진 확인 1명
#  - 그 밖의 값을 고치는 '정정 요청': 다른 사용자 2명
OWNER_DECLARATION_FIELDS = {"assistance_offered", "portable_ramp", "portable_ramp_length_cm"}
OWNER_DECLARATION_CONFIRMATIONS = 1
OWNER_CORRECTION_CONFIRMATIONS = 2


@dataclass
class Change:
    place: object
    profile: object
    before: str
    after: str

    @property
    def direction(self):
        # 미확인 → 어려움은 "새 정보"라서 하향으로 보지 않는다 (기존 판정을 깎는 게 아님)
        if self.before == Outcome.UNKNOWN:
            return UP if self.after in (Outcome.ACCESSIBLE, Outcome.CONDITIONAL) else SAME
        if self.after == Outcome.UNKNOWN:
            return SAME
        before, after = IMPROVEMENT_RANK[self.before], IMPROVEMENT_RANK[self.after]
        return DOWN if after < before else UP if after > before else SAME


def report_values(report):
    return {v.field_id: v.value for v in report.values.select_related("field")}


def report_effect(report):
    """
    이 제보를 반영했을 때 장소·이동 조건별 판정 변화 목록.
    새 장소 제안은 비교할 기존 판정이 없으므로 빈 목록.
    """
    if report.is_new_place:
        return []
    rule_set = RuleSet.active()
    if rule_set is None:
        return []
    overrides = {report.target: report_values(report)}
    changes = []
    for place in affected_places(report):
        for profile in ConditionProfile.objects.filter(is_active=True):
            before = judge(place, profile, rule_set).outcome
            after = judge(place, profile, rule_set, overrides=overrides).outcome
            changes.append(Change(place, profile, before, after))
    return changes


def report_direction(report, changes=None):
    """제보 전체의 방향: 하나라도 내려가면 DOWN, 아니면 하나라도 올라가면 UP, 아니면 SAME"""
    directions = {c.direction for c in (report_effect(report) if changes is None else changes)}
    if DOWN in directions:
        return DOWN
    if UP in directions:
        return UP
    return SAME


def is_owner_declaration(report):
    keys = set(report.values.values_list("field_id", flat=True))
    return bool(keys) and keys <= OWNER_DECLARATION_FIELDS


def required_confirmations(report):
    from reports.models import Report

    if report.source == Report.Source.OWNER:
        return OWNER_DECLARATION_CONFIRMATIONS if is_owner_declaration(report) else OWNER_CORRECTION_CONFIRMATIONS
    return REQUIRED_CONFIRMATIONS[report_direction(report)]
