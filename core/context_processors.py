from django.conf import settings


def kakao_keys(request):
    """카카오 JS 키를 모든 템플릿에 전달 (JS 키는 브라우저에 노출되는 용도라 공개돼도 됨).
    REST API 키는 절대 템플릿으로 내보내지 않습니다."""
    return {"KAKAO_JAVASCRIPT_KEY": settings.KAKAO_JAVASCRIPT_KEY}
