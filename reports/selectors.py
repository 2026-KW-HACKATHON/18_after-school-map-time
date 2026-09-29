"""
조회 함수 모음. "지금 화면·판정에 쓸 값"을 구하는 규칙을 한 곳에 둔다.

현재 값 = 대상·필드별로 VERIFIED 제보 중 가장 최근에 작성된(관찰한) 값.
PENDING 값은 판정에 쓰지 않고 "확인 중" 표시에만 쓴다 (기획 v2 OP-6).
"""

from .models import AccessibilityValue, Report


def _target_filter(target):
    from places.models import Building, Entrance, Place

    if isinstance(target, Entrance):
        return {"report__entrance": target}
    if isinstance(target, Building):
        return {"report__building": target}
    if isinstance(target, Place):
        return {"report__place": target}
    raise TypeError(f"지원하지 않는 대상: {type(target).__name__}")


def current_values(target):
    """{필드 키: AccessibilityValue} — 판정·상세 화면용 검증된 최신 값"""
    values = (
        AccessibilityValue.objects.filter(report__status=Report.Status.VERIFIED, **_target_filter(target))
        .select_related("field", "report")
        .order_by("field_id", "-report__created_at", "-id")
    )
    result = {}
    for v in values:
        result.setdefault(v.field_id, v)  # 필드별로 첫 번째(=가장 최근) 값만
    return result


def pending_fields(target):
    """확인 중인 제보가 있는 필드 키 집합 — "새 제보 확인 중" 표시용"""
    return set(
        AccessibilityValue.objects.filter(report__status=Report.Status.PENDING, **_target_filter(target))
        .values_list("field_id", flat=True)
    )
