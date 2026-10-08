"""개인화 입력·Preset 목록. 숫자 기본값은 활성 Rule에서만 읽고 판정값은 저장하지 않는다."""
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError

from places.validation import NUMERIC_LIMITS, validate_number
from .models import ConditionProfile, Outcome, Rule, RuleCondition, RuleSet

VERSION = 1
PRESETS = json.loads((Path(__file__).parent / "data" / "mobility_presets.json").read_text(encoding="utf8"))
PRESET_BY_KEY = {p["key"]: p for p in PRESETS}
COMPANIONS = {p["key"] for p in PRESETS if p.get("companion")}
NOTICE = "입력값은 자신의 이동 능력에 대한 자기평가이며 안전이나 실제 이용을 보장하지 않아요. 방문 전 현장과 도움 방법을 확인해 주세요."
FIELD_SPECS = {
    "max_step_height_cm": {"label": "통과 가능한 최대 턱 높이", "type": "number", "field": "step_height_cm", "unit": "cm", "help": "기존 제보의 입구 전체 단차 높이와 비교해요. 경사로·도움 경로는 따로 확인해요."},
    "min_door_width_cm": {"label": "필요한 최소 출입문 폭", "type": "number", "field": "door_width_cm", "unit": "cm"},
    "max_slope_deg": {"label": "허용 가능한 최대 경사", "type": "number", "field": "facility_slope_deg", "unit": "도", "help": "사용하는 경사로와 측정값의 연결이 확인되지 않으면 정보 없음으로 안내해요."},
    "can_use_stairs": {"label": "계단 이용 가능", "type": "bool", "help": "기본값은 기존 도움 조건을 포함한 규칙을 사용해요. 가능으로 바꿔도 다른 턱·폭 조건은 확인해요."},
    "needs_elevator": {"label": "층 이동 시 엘리베이터 필요", "type": "bool"},
    "needs_accessible_toilet": {"label": "장애인 화장실 필요", "type": "bool"},
    "needs_handrail": {"label": "계단·경사로의 난간 / 손잡이 필요", "type": "bool", "help": "경로 연결 정보가 부족하면 이용 가능으로 추정하지 않아요."},
    "min_passage_width_cm": {"label": "필요한 최소 실내 통로 폭", "type": "number", "field": "door_width_cm", "unit": "cm", "unsupported": True, "help": "실내 통로 폭 데이터는 아직 수집하지 않아요. 출입문 폭으로 대체하지 않아요."},
    "prefers_rest_seat": {"label": "휴식 좌석 선호", "type": "bool", "preference": True, "unsupported": True, "help": "선호 항목이며 접근 불가 판정을 만들지 않아요. 좌석 데이터 수집이 필요해요."},
}
FIELDS_BY_PRESET = {
    "WHEELCHAIR": ("max_step_height_cm", "min_door_width_cm", "max_slope_deg", "can_use_stairs", "needs_elevator", "needs_accessible_toilet"),
    "STROLLER": ("max_step_height_cm", "min_door_width_cm", "can_use_stairs", "needs_elevator"),
    "WALKER": ("max_step_height_cm", "min_passage_width_cm", "can_use_stairs", "max_slope_deg", "needs_elevator"),
    "CRUTCH": ("max_step_height_cm", "can_use_stairs", "max_slope_deg", "needs_handrail"),
    "LIMITED_WALKING": ("max_step_height_cm", "can_use_stairs", "max_slope_deg", "needs_handrail", "needs_elevator", "prefers_rest_seat"),
}


def base_preset(key, companions=None):
    p = PRESET_BY_KEY.get(key, {"profile": key})
    return (companions or {}).get(key, p["profile"]) if p.get("companion") else key


def profile_key(key, companions=None):
    actual = base_preset(key, companions)
    return PRESET_BY_KEY.get(actual, {"profile": actual})["profile"]


def field_keys(key, companions=None):
    return FIELDS_BY_PRESET.get(base_preset(key, companions), ("max_step_height_cm", "can_use_stairs"))


def active_presets():
    profiles = {p.key: p for p in ConditionProfile.objects.filter(is_active=True)}
    out = [deepcopy(p) for p in PRESETS if p["profile"] in profiles]
    for preset in out:
        if preset["key"] == preset["profile"]:
            preset["label"] = profiles[preset["profile"]].label
    known = {p["key"] for p in out}
    out.extend({"key": p.key, "label": p.label, "profile": p.key} for p in profiles.values() if p.key not in known)
    return out


def rule_defaults(profile):
    """기본 수치가 없는 항목은 None. 관측값 허용범위를 판정 임계값으로 쓰지 않는다."""
    defaults = {k: None for k in FIELD_SPECS}
    ruleset = RuleSet.active()
    if not ruleset:
        return defaults
    rules = ruleset.rules.filter(profile_id=profile).prefetch_related("conditions__field")
    for rule in rules:
        if rule.outcome != Outcome.ACCESSIBLE or rule.stage != Rule.Stage.ENTRANCE:
            continue
        for cond in rule.conditions.all():
            if cond.ref_field_id or cond.threshold is None:
                continue
            key = {"step_height_cm": "max_step_height_cm", "door_width_cm": "min_door_width_cm"}.get(cond.field_id)
            expected = RuleCondition.Operator.LTE if key == "max_step_height_cm" else RuleCondition.Operator.GTE
            if key and cond.operator == expected:
                defaults[key] = format(Decimal(cond.threshold).normalize(), "f")
    # 기존 계단·층 이동 규칙에는 도움 조건이 있어 bool로 단순화하지 않는다.
    return defaults


def catalogue():
    presets = active_presets()
    ruleset = RuleSet.active()
    options = [{"key": p["key"], "label": p["label"]} for p in presets if not p.get("companion")]
    fields = deepcopy(FIELD_SPECS)
    for spec in fields.values():
        if spec["type"] == "number":
            spec["min"], spec["max"] = NUMERIC_LIMITS[spec["field"]]
            spec["step"] = "0.1"
    return {"version": VERSION, "rule_version": ruleset.version if ruleset else None,
            "presets": [{**p, "fields": list(field_keys(p["key"])), "defaults": rule_defaults(p["profile"])} for p in presets],
            "companion_options": options, "fields": fields,
            "notice": NOTICE}


def default_settings():
    presets = active_presets()
    rule_set = RuleSet.active()
    return {"version": VERSION, "rule_version": rule_set.version if rule_set else None,
            "selected": [presets[0]["key"]] if presets else [], "overrides": {}, "companions": {}}


def normalize_settings(raw):
    """알 수 없는·비활성 Preset, 타입·범위 오류를 거부. GET 복원은 오류를 안내하고 기본값으로 대체한다."""
    if not isinstance(raw, dict) or set(raw) - {"version", "rule_version", "selected", "overrides", "companions"}:
        raise ValidationError("이동 조건 설정 형식을 확인해 주세요.")
    if type(raw.get("version")) is not int or raw["version"] != VERSION:
        raise ValidationError("지원하지 않는 이동 조건 설정 버전입니다.")
    presets = {p["key"]: p for p in active_presets()}
    selected = raw.get("selected")
    if not isinstance(selected, list) or not selected or len(selected) > len(presets):
        raise ValidationError("이동 조건을 하나 이상 선택해 주세요.")
    if any(not isinstance(k, str) or k not in presets for k in selected) or len(set(selected)) != len(selected):
        raise ValidationError("이동 조건이 중복되었거나 사용할 수 없어요.")
    companions = raw.get("companions", {})
    overrides = raw.get("overrides", {})
    if not isinstance(companions, dict) or not isinstance(overrides, dict):
        raise ValidationError("개인화 설정 형식을 확인해 주세요.")
    if any(not isinstance(v, str) or k not in COMPANIONS or k not in presets or v not in presets or v in COMPANIONS for k, v in companions.items()):
        raise ValidationError("동반자의 실제 이동 조건을 확인해 주세요.")
    normalized = {}
    for preset, values in overrides.items():
        if preset not in presets or not isinstance(values, dict) or set(values) - set(field_keys(preset, companions)):
            raise ValidationError("이 Preset에서 지원하지 않는 설정 항목입니다.")
        clean = {}
        for key, value in values.items():
            if value is None:  # 이 항목의 Override 초기화
                continue
            spec = FIELD_SPECS[key]
            if spec["type"] == "bool":
                if type(value) is not bool:
                    raise ValidationError(f"{spec['label']}: 가능·필요 여부를 확인해 주세요.")
                clean[key] = value
            else:
                number = validate_number(spec["field"], value, spec["label"])
                if number.as_tuple().exponent < -1:
                    raise ValidationError(f"{spec['label']}: 소수점 한 자리까지 입력해 주세요.")
                clean[key] = format(number.normalize(), "f")
        if clean:
            normalized[preset] = clean
    version = raw.get("rule_version")
    if version is not None and (type(version) is not int or version < 1):
        raise ValidationError("기본 판정 기준 버전을 확인해 주세요.")
    return {"version": VERSION, "rule_version": version, "selected": list(selected),
            "overrides": normalized, "companions": dict(companions)}


def requirements(settings):
    profiles = {p.key: p for p in ConditionProfile.objects.filter(is_active=True)}
    return [(profiles[profile_key(key, settings["companions"])], deepcopy(settings["overrides"].get(key, {})))
            for key in settings["selected"]]


def merged_constraints(settings):
    """같은 경로에 적용할 더 엄격한 조건. 개별 저장값은 변경하지 않는다."""
    out = {}
    for key in settings["selected"]:
        values = {k: v for k, v in rule_defaults(profile_key(key, settings["companions"])).items() if v is not None}
        values.update(settings["overrides"].get(key, {}))
        for field, value in values.items():
            if field in ("max_step_height_cm", "max_slope_deg"):
                out[field] = format(min(Decimal(out.get(field, value)), Decimal(value)).normalize(), "f")
            elif field in ("min_door_width_cm", "min_passage_width_cm"):
                out[field] = format(max(Decimal(out.get(field, value)), Decimal(value)).normalize(), "f")
            elif field == "can_use_stairs":
                out[field] = out.get(field, True) and value
            elif field.startswith("needs_") or field == "prefers_rest_seat":
                out[field] = out.get(field, False) or value
    return out
