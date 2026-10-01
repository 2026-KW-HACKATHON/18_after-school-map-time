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


def is_photo_request(report):
    """
    사진 교체·수정 요청 (기획 v2 4.4) — 운영자만 처리
      - 사장님: 값 없이 사진만 담은 사장님 요청
      - 주민: 설명이 '[사진 수정 요청]'으로 시작하는 주민 제보 (예전 모습, 내 얼굴·지인 얼굴이 나옴 등)
    """
    from reports.models import PHOTO_FIX_PREFIX, Report

    if report.source == Report.Source.OWNER:
        return not report.values.exists()
    return report.source == Report.Source.USER_REPORT and report.note.startswith(PHOTO_FIX_PREFIX)


def required_confirmations(report):
    """
    반영에 필요한 주민 확인 수. None = 주민 확인으로는 반영하지 않고 운영자만 처리:
      - 사진 교체 요청: 얼굴·번호판이 없는지 운영자가 봐야 함 (기획 v2 4.4)
      - 가입 7일 미만 계정의 판정 하향 제보: 관리자 검수 큐로 (기획 v2 7장)
    """
    from reports.models import Report

    if is_photo_request(report):
        return None
    if report.source == Report.Source.OWNER:
        return OWNER_DECLARATION_CONFIRMATIONS if is_owner_declaration(report) else OWNER_CORRECTION_CONFIRMATIONS
    direction = report_direction(report)
    author = report.created_by
    if direction == DOWN and author is not None and author.is_new_account(now=report.created_at):
        return None
    return REQUIRED_CONFIRMATIONS[direction]
