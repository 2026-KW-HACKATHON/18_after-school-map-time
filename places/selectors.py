"""
화면·API가 같이 쓰는 장소 조회 함수. 표시 정책(기획 v2 3장)은 여기서 한 번만 적용한다.
"""

from django.db.models import Max, Q

from judgments.constants import display
from judgments.models import ConditionProfile, Judgment, Outcome
from reports.models import Report
from reports.selectors import conflicting_fields, current_values, latest_photo, pending_field_sources

from .models import FieldDefinition, Place

# 목록·팝업·검색 결과에 보여줄 입구 핵심 값 (순서대로)
SUMMARY_FIELDS = ["step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type"]


def _explanation(result, reason, rule):
    """판단 근거 문장 (와이어프레임 7번 '이동 조건 판단 근거'). 평가가 아니라 사실과 기준을 말한다 (OP-1)"""
    if result == Outcome.UNKNOWN:
        return "아직 확인된 입구 정보가 부족해요. 알고 계시면 알려주세요."
    parts = []
    if reason:
        parts.append(f"확인된 사실: {reason}.")
    if rule is not None:
        parts.append(f"적용 기준({rule.get_basis_display()}): {rule.note}" if rule.note else f"적용 기준: {rule.get_basis_display()}")
    if result == Outcome.DIFFICULT:
        parts.append("다른 출입구나 도움 요청 방법이 있는지 아래에서 확인해 보세요.")  # OP-2
    return " ".join(parts)


def judgment_payload(judgment):
    if judgment is None:
        return None
    rule = judgment.matched_rule
    return {
        **display(judgment.result),
        "reason": judgment.reason,
        "improved": judgment.has_improved_badge,
        "rule_version": judgment.rule_version,
        "basis": rule.basis if rule else None,
        "basis_label": rule.get_basis_display() if rule else None,
        "explanation": _explanation(judgment.result, judgment.reason, rule),
    }


def unknown_payload():
    return {**display(Outcome.UNKNOWN), "reason": "", "improved": False, "rule_version": None,
            "basis": None, "basis_label": None, "explanation": _explanation(Outcome.UNKNOWN, "", None)}


def map_places(region, profile=None, show_all=False):
    """
    지도·목록용 장소 목록.
    - 이동 조건을 고르면 기본으로 '들어갈 수 있어요'·'도움 받으면'만 (어려움·미확인은 숨김, 기획 v2 3.2)
    - 접근성 낮은 순 정렬·"어려운 곳만 보기"는 만들지 않는다. 정렬은 화면에서 거리순
    """
    places = Place.objects.in_region(region).filter(is_closed=False).order_by("name")
    judgments = {}
    if profile is not None:
        judgments = {
            j.place_id: j
            for j in Judgment.objects.filter(place__in=places, profile=profile).select_related("matched_rule")
        }

    rows = []
    for place in places:
        payload = None
        if profile is not None:
            payload = judgment_payload(judgments.get(place.id)) or unknown_payload()
            if payload["hidden_by_default"] and not show_all:
                continue
        rows.append({"place": place, "judgment": payload})
    return rows


def _place_reports(place):
    """이 장소 화면에 관련된 제보: 장소·장소 출입구·건물·건물 출입구"""
    q = Q(place=place) | Q(entrance__place=place)
    if place.building_id:
        q |= Q(building_id=place.building_id) | Q(entrance__building_id=place.building_id)
    return Report.objects.filter(q)


def place_summary(place):
    """검색 결과·팝업용 요약: 주 출입구 핵심 값 한 줄 + 마지막 확인 시각"""
    entrance = place.entrances.filter(is_main=True).first() or place.entrances.first()
    facts = []
    if entrance is not None:
        values = current_values(entrance)
        for key in SUMMARY_FIELDS:
            v = values.get(key)
            if v is not None:
                facts.append(f"{v.field.label} {v.display_value}{v.field.unit if v.field.unit else ''}")
    last = _place_reports(place).filter(status=Report.Status.VERIFIED).aggregate(last=Max("observed_at"))["last"]
    return {"facts": " · ".join(facts), "last_checked": last}


def _fields_section(target, scope):
    """대상의 필드 값 목록 (검증된 값 + '확인 중' 표시)"""
    if target is None:
        return []
    values = current_values(target)
    pending = pending_field_sources(target)
    rows = []
    for f in FieldDefinition.objects.filter(scope=scope, is_active=True):
        v = values.get(f.key)
        rows.append({
            "key": f.key,
            "label": f.label,
            "value": v.display_value if v else None,
            "unit": f.unit if v and f.unit else "",
            "checked_at": v.report.observed_at if v else None,
            "pending": f.key in pending,  # "새 제보 확인 중" (기획 v2 7장)
            "pending_owner": pending.get(f.key) == Report.Source.OWNER,  # "사장님이 정정을 요청했어요"
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


def _pending_reports(place):
    """확인 중인 주민 제보 (장소 상세에서 다른 주민이 '맞아요'로 확인)"""
    from judgments.services import required_confirmations

    reports = (
        _place_reports(place)
        .filter(status=Report.Status.PENDING, source__in=[Report.Source.USER_REPORT, Report.Source.OWNER])
        .select_related("entrance", "created_by")
        .prefetch_related("values__field")
        .order_by("-created_at")
    )
    rows = []
    for r in reports:
        required = required_confirmations(r)
        if required is None:
            continue  # 운영자만 처리하는 요청(사진 교체)은 주민 확인 목록에 넣지 않음
        rows.append({
            "report": r,
            "values": list(r.values.all()),
            "confirmations": r.confirmations.count(),
            "required": required,
        })
    return rows


def building_common_section(building):
    """건물 공용 입구·시설 (장소 상세와 건물주 화면에서 같이 씀)"""
    return {
        "building": building,
        "entrances": _entrances_section(building.entrances.all()),
        "fields": _fields_section(building, FieldDefinition.Scope.BUILDING),
    }


def place_detail(place):
    """
    장소 상세. 건물 공용 정보와 가게 정보를 섹션으로 나눈다 (기획 v2 5.1, OP-4).
    """
    judgments = {j.profile_id: j for j in Judgment.objects.filter(place=place).select_related("matched_rule")}
    profiles = ConditionProfile.objects.filter(is_active=True)
    building = place.building

    building_section = building_common_section(building) if building else None
    place_section = {
        "entrances": _entrances_section(place.entrances.all()),
        "fields": _fields_section(place, FieldDefinition.Scope.PLACE),
    }

    # 마지막 확인일 (F4): 이 장소 화면에 나온 모든 값 중 가장 최근 확인 시각
    sections = [place_section] + ([building_section] if building_section else [])
    all_fields = [f for s in sections for f in s["fields"]]
    all_fields += [f for s in sections for e in s["entrances"] for f in e["fields"]]
    checked = [f["checked_at"] for f in all_fields if f["checked_at"]]

    verified = _place_reports(place).filter(status=Report.Status.VERIFIED)
    sources = [Report.Source(s).label for s in verified.values_list("source", flat=True).distinct().order_by("source")]

    return {
        "place": place,
        "judgments": [
            {"profile": p, "judgment": judgment_payload(judgments.get(p.key)) or unknown_payload()}
            for p in profiles
        ],
        "building": building_section,
        "place_section": place_section,
        "last_checked": max(checked) if checked else None,
        "sources": sources,  # 정보 신뢰도: 출처 (와이어프레임 7번)
        # 긍정 배지 '도움 제공 가게' (OP-5): 확인된 사장님 선언이 있을 때만
        "assistance_badge": getattr(current_values(place).get("assistance_offered"), "value", None) is True,
        "verified_user_reports": verified.filter(source=Report.Source.USER_REPORT).count(),
        "pending_reports": _pending_reports(place),
        "conflicts": place_conflicts(place),
    }


def place_conflicts(place):
    """가게·출입구·건물에서 사장님 정보와 주민 제보가 다른 항목 이름 (기획 v2 7장)"""
    targets = [place, *place.entrances.all()]
    if place.building_id:
        targets += [place.building, *place.building.entrances.all()]
    labels = []
    for target in targets:
        for f in conflicting_fields(target):
            if f.label not in labels:
                labels.append(f.label)
    return labels
