"""로그인 회원 자신의 설정만 저장·복원한다. 요청에 회원 ID를 받지 않는다."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from judgments.mobility import default_settings, normalize_settings
from .models import MobilityPreference


def _response(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


def restored_settings(user):
    warning = ""
    saved = MobilityPreference.objects.filter(user=user).first() if user.is_authenticated else None
    defaults = default_settings()
    if saved is None:
        return defaults, warning
    try:
        data = normalize_settings(saved.data)
    except DjangoValidationError:
        return defaults, "저장된 이동 조건을 복원할 수 없어 기본 설정을 표시해요. 다시 저장하면 복구할 수 있어요."
    if data["rule_version"] != defaults["rule_version"]:
        warning = "기본 판정 기준이 바뀌었어요. 입력한 Override는 유지하고 수정하지 않은 항목은 최신 기본값을 사용해요."
    return data, warning


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def preferences(request):
    if request.method == "GET":
        data, warning = restored_settings(request.user)
        return _response({"settings": data, "warning": warning})
    if request.method == "DELETE":
        MobilityPreference.objects.filter(user=request.user).delete()
        return _response({"settings": default_settings(), "warning": ""})
    try:
        data = normalize_settings(request.data)
        data["rule_version"] = default_settings()["rule_version"]
        preference = MobilityPreference.objects.filter(user=request.user).first() or MobilityPreference(user=request.user)
        preference.data = data
        preference.save()
    except DjangoValidationError as error:
        return _response({"detail": " ".join(error.messages)}, status=400)
    return _response({"settings": preference.data, "warning": ""})
