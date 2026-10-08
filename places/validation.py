"""관측값의 입력 범위. 판정 기준(Rule)과 별개인 Form / Model 공통 검증이다."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError


# 기존 Form의 허용 범위를 유지한다. 새 NUMBER 정의도 기본적으로 음수는 금지한다.
NUMERIC_LIMITS = {
    "step_height_cm": (0, 500),
    "step_count": (0, 50),
    "door_width_cm": (0, 1000),
    "portable_ramp_length_cm": (0, 1000),
    "facility_door_width_cm": (0, 1000),
    "facility_step_count": (0, 10000),
    "facility_width_cm": (0, 1000),
    "facility_slope_deg": (0, 90),
}
INTEGER_KEYS = {"step_count", "facility_step_count"}


def numeric_form_options(key):
    minimum, maximum = NUMERIC_LIMITS.get(key, (0, None))
    return {"min_value": minimum, "max_value": maximum}


def validate_number(key, raw, label):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label}: 숫자를 입력하세요.")
    if not value.is_finite():
        raise ValidationError(f"{label}: 유한한 숫자를 입력하세요.")
    minimum, maximum = NUMERIC_LIMITS.get(key, (0, None))
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f"{minimum} 이상" if maximum is None else f"{minimum} 이상 {maximum} 이하"
        raise ValidationError(f"{label}: {bounds}이어야 합니다.")
    if key in INTEGER_KEYS and value != value.to_integral_value():
        raise ValidationError(f"{label}: 정수를 입력하세요.")
    return value


def parse_boolean(raw):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in ("true", "1", "yes", "y", "있음", "예"):
            return True
        if token in ("false", "0", "no", "n", "없음", "아니오", "아니요"):
            return False
    raise ValidationError("예/아니오 값이 올바르지 않습니다.")
