"""기존 경로 평가에 더하는 개인 필수 조건. 시설 존재와 실제 경로 연결을 혼동하지 않는다."""
import re
from decimal import Decimal

from places.models import AccessFacility
from reports.selectors import current_values
from .models import Outcome


def _values(target):
    return {k: v.value for k, v in current_values(target).items()} if target is not None else {}


def _connected(text, floor):
    """명시적으로 기록된 층만 인식. 불명확한 자유 텍스트로 경로를 추정하지 않는다."""
    tokens = set()
    for underground, number in re.findall(r"(지하\s*|B\s*|-)?(\d+)\s*(?:층|F)", text or "", re.I):
        tokens.add(-int(number) if underground else int(number))
    return 1 in tokens and floor in tokens


def facility_fact(place, kind, wheelchair=False, connected=False):
    """검증된 시설의 이용 가능성: True / 명시적 False / 모름. 미등록은 False가 아니다."""
    from django.db.models import Q
    owners = Q(place=place)
    if place.building_id:
        owners |= Q(building=place.building)
    facilities = AccessFacility.objects.filter(owners, kind=kind)
    observations = []
    for facility in facilities:
        facts = _values(facility)
        value = facts.get("facility_available")
        if value is True:
            if wheelchair and facts.get("facility_wheelchair") is not True:
                value = False if facts.get("facility_wheelchair") is False else None
            if connected and not _connected(facts.get("facility_connected_floors"), place.floor):
                value = None
        observations.append(value)
    if True in observations:
        return True
    return False if observations and all(v is False for v in observations) else None


def elevator_fact(place, subject):
    legacy = subject.building_values.get("elevator")
    facility = facility_fact(place, AccessFacility.Kind.ELEVATOR, connected=True)
    # 기존 건물의 명시적 관측값 또는 연결 층이 확인된 E/V. 미등록·일부 누락은 없음으로 보지 않는다.
    if legacy is True or facility is True:
        return True
    return False if legacy is False and facility is not True else None


def accessible_toilet_fact(place, subject):
    legacy = [subject.place_values.get("accessible_toilet"), subject.building_values.get("building_accessible_toilet")]
    facility = facility_fact(place, AccessFacility.Kind.TOILET, wheelchair=True)
    if True in legacy or facility is True:
        return True
    if legacy[0] is False and (not place.building_id or legacy[1] is False):
        return False
    return False if facility is False and all(v is False for v in legacy) else None


def extra_requirements(place, subject, criteria, result, rules):
    """(outcome, reason) 또는 None. 선호 항목은 이 필수 조건 평가에 넣지 않는다."""
    if not criteria:
        return None
    if subject.is_floor:
        if criteria.get("needs_elevator") is True or criteria.get("can_use_stairs") is False:
            value = elevator_fact(place, subject)
            if value is not True:
                return (Outcome.DIFFICULT if value is False else Outcome.UNKNOWN, "필요한 엘리베이터 정보를 확인할 수 없어요." if value is None else "필요한 엘리베이터가 없다고 확인됐어요.")
        elif criteria.get("needs_elevator") is False and result.outcome != Outcome.ACCESSIBLE:
            # 필요하지 않다는 입력만으로 계단 경로가 존재한다고 추정하지 않는다.
            floor_rules = [r for r in rules if r.stage == "FLOOR"]
            only_elevator = all(c.field_id == "elevator" for r in floor_rules for c in r.conditions.all())
            if only_elevator and criteria.get("can_use_stairs") is True and facility_fact(place, AccessFacility.Kind.STAIRS, connected=True) is True:
                return (Outcome.ACCESSIBLE, "연결 층이 확인된 계단과 입력한 계단 이용 가능 조건을 적용했어요.")
            return (Outcome.UNKNOWN, "엘리베이터 외에 사용할 층 이동 경로 정보가 부족해요.")
        return None

    ramp_rule = result.rule and any(c.field_id in ("has_ramp", "portable_ramp") for c in result.rule.conditions.all())
    if "max_step_height_cm" in criteria and not ramp_rule:
        height = subject.values.get("step_height_cm")
        if height is None:
            return (Outcome.UNKNOWN, "입력한 최대 턱 높이와 비교할 정보가 없어요.")
        if Decimal(height) > Decimal(criteria["max_step_height_cm"]):
            return (Outcome.DIFFICULT, f"입구 단차 {height}cm · 내 최대 높이 {criteria['max_step_height_cm']}cm")
    if "min_door_width_cm" in criteria:
        width = subject.values.get("door_width_cm")
        if width is None:
            return (Outcome.UNKNOWN, "필요한 출입문 폭을 비교할 정보가 없어요.")
        if Decimal(width) < Decimal(criteria["min_door_width_cm"]):
            return (Outcome.DIFFICULT, f"출입문 폭 {width}cm · 내 최소 폭 {criteria['min_door_width_cm']}cm")
    if criteria.get("can_use_stairs") is False:
        count = subject.values.get("step_count")
        if subject.values.get("has_ramp") is not True and not ramp_rule:
            if count is None:
                return (Outcome.UNKNOWN, "계단을 피할 수 있는지 확인할 정보가 없어요.")
            if Decimal(count) > 0:
                return (Outcome.DIFFICULT, "계단 이용 불가로 설정했으며 이 입구에 계단이 있어요.")
    if criteria.get("max_slope_deg") is not None and ramp_rule:
        return (Outcome.UNKNOWN, "이 입구 경사로와 확인된 경사 측정값의 연결 정보가 없어요.")
    uses_stairs = Decimal(subject.values.get("step_count") or 0) > 0
    if criteria.get("needs_handrail") is True and subject.values.get("step_count") is None:
        return (Outcome.UNKNOWN, "난간이 필요한 계단 경로인지 확인할 정보가 없어요.")
    if criteria.get("needs_handrail") is True and (uses_stairs or ramp_rule or (place.floor != 1 and elevator_fact(place, subject) is not True)):
        return (Outcome.UNKNOWN, "사용할 계단·경사로와 난간 정보의 연결이 아직 확인되지 않았어요.")
    if criteria.get("min_passage_width_cm") is not None:
        return (Outcome.UNKNOWN, "실내 통로 폭 데이터 수집이 필요해요. 출입문 폭으로 대체하지 않아요.")
    if criteria.get("needs_accessible_toilet") is True:
        value = accessible_toilet_fact(place, subject)
        if value is not True:
            return (Outcome.DIFFICULT if value is False else Outcome.UNKNOWN, "필요한 장애인 화장실 정보를 확인할 수 없어요." if value is None else "필요한 장애인 화장실을 이용할 수 없다고 확인됐어요.")
    return None
