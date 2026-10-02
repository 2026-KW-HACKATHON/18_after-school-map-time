"""
조회 함수 모음. "지금 화면·판정에 쓸 값"을 구하는 규칙을 한 곳에 둔다.

현재 값 = 대상·필드별로 VERIFIED 제보 중 가장 최근에 확인한(observed_at) 값.
PENDING 값은 판정에 쓰지 않고 "확인 중" 표시에만 쓴다 (기획 v2 OP-6).
"""

from .models import AccessibilityValue, Report


def _target_filter(target, prefix="report__"):
    """대상(장소·건물·출입구)으로 거르는 조건. Report를 직접 거를 땐 prefix="""""
    from places.models import AccessFacility, Building, Entrance, Place

    for model, name in ((AccessFacility, "facility"), (Entrance, "entrance"), (Building, "building"), (Place, "place")):
        if isinstance(target, model):
            return {f"{prefix}{name}": target}
    raise TypeError(f"지원하지 않는 대상: {type(target).__name__}")


def current_values(target):
    """{필드 키: AccessibilityValue} — 판정·상세 화면용 검증된 최신 값"""
    values = (
        AccessibilityValue.objects.filter(report__status=Report.Status.VERIFIED, **_target_filter(target))
        .select_related("field", "report")
        .order_by("field_id", "-report__observed_at", "-report__created_at", "-id")
    )
    result = {}
    for v in values:
        result.setdefault(v.field_id, v)  # 필드별로 첫 번째(=가장 최근) 값만
    return result


def latest_photo(target):
    """검증된 제보 중 가장 최근 사진 (없으면 None)"""
    report = (
        Report.objects.filter(status=Report.Status.VERIFIED, **_target_filter(target, prefix=""))
        .exclude(photo="")
        .order_by("-observed_at", "-created_at", "-id")
        .first()
    )
    return report.photo if report else None


def pending_field_sources(target):
    """{필드 키: 출처} — 확인 중인 제보가 있는 필드. 사장님 정정이면 '사장님이 정정을 요청했어요' 표시 (기획 v2 4.3)"""
    rows = (
        AccessibilityValue.objects.filter(report__status=Report.Status.PENDING, **_target_filter(target))
        .values_list("field_id", "report__source")
    )
    out = {}
    for key, source in rows:
        # 사장님 정정이 하나라도 있으면 그걸 우선 표시
        if out.get(key) != Report.Source.OWNER:
            out[key] = source
    return out


# 서로 다른 쪽의 정보 (기획 v2 7장 "사장님 선언과 사용자 제보가 충돌")
OWNER_SIDE = {Report.Source.OWNER}
RESIDENT_SIDE = {Report.Source.USER_REPORT}


def conflicting_fields(target):
    """
    사장님 정보와 주민 제보가 서로 다른 필드 [FieldDefinition] (기획 v2 7장).
    반영된 최신 값과 확인 중인 값을 모아, 한 필드에 사장님 쪽 값과 주민 쪽 값이 있고 서로 다르면 충돌.
    운영진이 판단하기 전까지 화면에 "정보가 서로 달라요, 방문 전 전화 확인을 권해요"를 띄우는 데 쓴다.
    """
    by_field = {}
    for key, v in current_values(target).items():
        by_field.setdefault(key, []).append((v.report.source, v.value, v.field))
    pending = AccessibilityValue.objects.filter(report__status=Report.Status.PENDING, **_target_filter(target))
    for v in pending.select_related("field", "report"):
        by_field.setdefault(v.field_id, []).append((v.report.source, v.value, v.field))
    conflicts = []
    for entries in by_field.values():
        owner = {value for source, value, _ in entries if source in OWNER_SIDE}
        resident = {value for source, value, _ in entries if source in RESIDENT_SIDE}
        if owner and resident and owner != resident:
            conflicts.append(entries[0][2])
    return sorted(conflicts, key=lambda f: f.order)


def pending_fields(target):
    """확인 중인 제보가 있는 필드 키 집합 — "새 제보 확인 중" 표시용"""
    return set(pending_field_sources(target))
