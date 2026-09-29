"""
화면·API가 같이 쓰는 장소 조회 함수. 표시 정책(기획 v2 3장)은 여기서 한 번만 적용한다.
"""

from judgments.constants import display
from judgments.models import ConditionProfile, Judgment
from reports.selectors import current_values, latest_photo, pending_fields

from .models import FieldDefinition, Place


def judgment_payload(judgment):
    if judgment is None:
        return None
    return {
        **display(judgment.result),
        "reason": judgment.reason,
        "improved": judgment.has_improved_badge,
        "rule_version": judgment.rule_version,
    }


def map_places(region, profile=None, show_all=False):
    """
    지도·목록용 장소 목록.
    - 이동 조건을 고르면 기본으로 '들어갈 수 있어요'·'도움 받으면'만 (어려움·미확인은 숨김, 기획 v2 3.2)
    - 접근성 낮은 순 정렬·"어려운 곳만 보기"는 만들지 않는다. 정렬은 화면에서 거리순
    """
    places = Place.objects.in_region(region).filter(is_closed=False).order_by("name")
    judgments = {}
    if profile is not None:
        judgments = {j.place_id: j for j in Judgment.objects.filter(place__in=places, profile=profile)}

    rows = []
    for place in places:
        judgment = judgments.get(place.id)
        payload = judgment_payload(judgment) if profile else None
        if profile and payload is None:
            payload = {**display("UNKNOWN"), "reason": "", "improved": False, "rule_version": None}
        if profile and payload["hidden_by_default"] and not show_all:
            continue
        rows.append({"place": place, "judgment": payload})
    return rows


def _fields_section(target, scope):
    """대상의 필드 값 목록 (검증된 값 + '확인 중' 표시)"""
    if target is None:
        return []
    values = current_values(target)
    pending = pending_fields(target)
    rows = []
    for f in FieldDefinition.objects.filter(scope=scope, is_active=True):
        v = values.get(f.key)
        rows.append({
            "key": f.key,
            "label": f.label,
            "value": v.display_value if v else None,
            "unit": f.unit if v and f.unit else "",
            "checked_at": v.report.created_at if v else None,
            "pending": f.key in pending,  # "새 제보 확인 중" (기획 v2 7장)
        })
    return rows


def _entrances_section(entrances):
    return [
        {
            "id": e.id,
            "name": e.name,
            "is_main": e.is_main,
            "description": e.description,
            "photo": latest_photo(e),  # 입구 사진 (F4) — 검증된 제보 중 가장 최근 사진
            "fields": _fields_section(e, FieldDefinition.Scope.ENTRANCE),
        }
        for e in entrances
    ]


def place_detail(place):
    """
    장소 상세. 건물 공용 정보와 가게 정보를 섹션으로 나눈다 (기획 v2 5.1, OP-4).
    """
    judgments = {j.profile_id: j for j in Judgment.objects.filter(place=place)}
    profiles = ConditionProfile.objects.filter(is_active=True)
    building = place.building

    building_section = {
        "building": building,
        "entrances": _entrances_section(building.entrances.all()),
        "fields": _fields_section(building, FieldDefinition.Scope.BUILDING),
    } if building else None
    place_section = {
        "entrances": _entrances_section(place.entrances.all()),
        "fields": _fields_section(place, FieldDefinition.Scope.PLACE),
    }

    # 마지막 확인일 (F4): 이 장소 화면에 나온 모든 값 중 가장 최근 확인 시각
    sections = [place_section] + ([building_section] if building_section else [])
    all_fields = [f for s in sections for f in s["fields"]]
    all_fields += [f for s in sections for e in s["entrances"] for f in e["fields"]]
    checked = [f["checked_at"] for f in all_fields if f["checked_at"]]

    return {
        "place": place,
        "judgments": [
            {"profile": p, "judgment": judgment_payload(judgments.get(p.key)) or {**display("UNKNOWN"), "reason": ""}}
            for p in profiles
        ],
        "building": building_section,
        "place_section": place_section,
        "last_checked": max(checked) if checked else None,
    }
