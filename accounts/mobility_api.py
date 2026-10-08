"""
로그인 회원 자신의 설정만 저장·복원한다. 요청에 회원 ID를 받지 않는다.

이동 조건(휠체어 등)은 몸 상태를 짐작할 수 있는 정보라 계정에 저장하려면 따로 동의를 받는다 (개인정보 보호법 제15조·제23조).
  - 저장(PUT)은 요청에 consent: true 가 있을 때만 한다. 그래서 저장된 행이 있다 = 동의했다 (updated_at = 마지막으로 동의하고 저장한 시각)
  - 철회는 DELETE: 저장된 행을 바로 지운다
  - 동의하지 않은 회원은 비회원처럼 브라우저(localStorage)에만 저장한다 (static/js/mobility-settings.js)
"""
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


CONSENT_REQUIRED = "내 계정에 저장하려면 개인정보(민감정보) 수집·이용 동의에 체크해 주세요. 동의하지 않으면 이 브라우저에만 저장돼요."


def has_consent(user):
    """계정 저장에 동의했는지. 동의 없이는 저장되지 않으므로 저장된 행이 있으면 동의한 것"""
    return user.is_authenticated and MobilityPreference.objects.filter(user=user).exists()


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
        warning = "기본 판정 기준이 바뀌었어요. 직접 바꾼 값은 유지하고, 바꾸지 않은 항목은 최신 기본값을 사용해요."
    return data, warning


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def preferences(request):
    if request.method == "GET":
        data, warning = restored_settings(request.user)
        return _response({"settings": data, "warning": warning, "consented": has_consent(request.user)})
    if request.method == "DELETE":
        # 동의 철회 = 저장된 이동 조건 삭제
        MobilityPreference.objects.filter(user=request.user).delete()
        return _response({"settings": default_settings(), "warning": "", "consented": False})
    body = dict(request.data) if isinstance(request.data, dict) else request.data
    if not isinstance(body, dict) or body.pop("consent", None) is not True:
        return _response({"detail": CONSENT_REQUIRED}, status=400)
    try:
        data = normalize_settings(body)
        data["rule_version"] = default_settings()["rule_version"]
        preference = MobilityPreference.objects.filter(user=request.user).first() or MobilityPreference(user=request.user)
        preference.data = data
        preference.save()
    except DjangoValidationError as error:
        return _response({"detail": " ".join(error.messages)}, status=400)
    return _response({"settings": preference.data, "warning": "", "consented": True})
