from django import template

register = template.Library()

# 운영자 화면의 제보 상태 표현 (와이어프레임: 대기 중 / 승인됨 / 반려됨)
OPS_STATUS_LABELS = {"PENDING": "대기 중", "VERIFIED": "승인됨", "REJECTED": "반려됨"}


@register.filter
def ops_status(report):
    """{{ report|ops_status }} — 모델의 '반영됨'을 운영자 화면에서는 '승인됨'으로"""
    return OPS_STATUS_LABELS.get(report.status, report.get_status_display())


@register.simple_tag
def ops_pending_counts():
    """운영자 메뉴 배지·폴링의 시작 숫자 {"pending", "claims"}"""
    from ops.views import pending_counts

    return pending_counts()
