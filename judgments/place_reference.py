"""방문 장소의 확인값을 설정 초안으로 제시한다. 이동 능력이나 방문 이력을 추론·저장하지 않는다."""
from decimal import Decimal

from django.core.exceptions import ValidationError

from reports.selectors import current_values, pending_fields
from places.validation import validate_number
from .engine import build_routes, floor_label

MEASUREMENTS = {"step_height_cm": "max_step_height_cm", "door_width_cm": "min_door_width_cm"}
NOTICE = "직접 이용한 입구 경로의 확인값만 참고하세요. 방문 경험은 최대 이동 능력이나 안전을 보장하지 않아요. 계단 이용 능력·시설 필요 여부는 직접 설정해 주세요."


def place_reference(place):
    observations = {}

    def entrance_data(entrance):
        if entrance.pk in observations:
            return observations[entrance.pk]
        values = current_values(entrance)
        pending = pending_fields(entrance)
        fields, numbers, excluded = [], {}, []
        for key in (*MEASUREMENTS, "step_count", "has_ramp", "entrance_available"):
            value = values.get(key)
            if value is None or not value.field.is_active:
                continue
            raw = value.value
            if raw is None:
                continue
            shown = format(raw.normalize(), "f") if isinstance(raw, Decimal) else raw
            fields.append({"key": key, "label": value.field.label, "value": shown,
                           "unit": value.field.unit, "checked_at": value.report.observed_at.isoformat(),
                           "pending": key in pending})
            if key in MEASUREMENTS and key not in pending:
                try:
                    number = validate_number(key, raw, value.field.label).normalize()
                    # 개인화 입력은 소수점 한 자리다. 관측값을 임의로 반올림하지 않는다.
                    if number.as_tuple().exponent >= -1:
                        numbers[MEASUREMENTS[key]] = format(number, "f")
                    else:
                        excluded.append(f"{value.field.label}: 소수점 한 자리 입력에 맞춰 임의로 반올림하지 않아 참고값에서 제외했어요.")
                except ValidationError:
                    excluded.append(f"{value.field.label}: 현재 입력 범위를 벗어난 과거 값이라 참고값에서 제외했어요.")
        availability = values.get("entrance_available")
        result = {"entrance_id": entrance.pk,
                  "label": f"{'건물 공용' if entrance.building_id else '장소'} · {entrance.name}",
                  "fields": fields, "numbers": numbers, "excluded": excluded,
                  "unavailable": bool(availability and availability.field.is_active and availability.value is False)}
        observations[entrance.pk] = result
        return result

    # 기존 판정 엔진과 같은 출입구 조합을 사용한다. 서로 다른 최적 입구를 섞지 않는다.
    routes = []
    incomplete = place.floor != 1 and (not place.building_id or not place.building.entrances.exists() or not place.entrances.exists())
    for subjects in build_routes(place, with_floor=True):
        entrances = [entrance_data(s.entrance) for s in subjects if s.entrance is not None]
        labels = [floor_label(s.floor) if s.is_floor else entrance_data(s.entrance)["label"] for s in subjects]
        unavailable = any(e["unavailable"] for e in entrances)
        numbers = {}
        if not incomplete and not unavailable:
            for key, combine in (("max_step_height_cm", max), ("min_door_width_cm", min)):
                if entrances and all(key in e["numbers"] for e in entrances):
                    numbers[key] = format(combine(Decimal(e["numbers"][key]) for e in entrances).normalize(), "f")
        warnings = [message for e in entrances for message in e["excluded"]]
        if incomplete:
            warnings.append("건물 공용 입구 또는 가게 입구가 미등록이라 전체 경로의 참고값을 제공할 수 없어요.")
        if unavailable:
            warnings.append("현재 이용 불가로 확인된 입구가 있어 참고값을 적용할 수 없어요.")
        if any(s.values.get("has_ramp") is True or s.place_values.get("portable_ramp") is True for s in subjects):
            warnings.append("경사로 정보가 있어요. 경사로·도움을 이용했다면 턱 높이를 직접 통과한 값으로 적용하지 마세요.")
        if any(field["pending"] for e in entrances for field in e["fields"]):
            warnings.append("새 제보가 확인 중인 측정 항목은 참고값에서 제외했어요.")
        routes.append({"id": "/".join(f"floor:{s.floor}" if s.is_floor else f"entrance:{s.entrance.pk}" for s in subjects),
                       "label": " → ".join(labels),
                       "entrances": [{k: e[k] for k in ("entrance_id", "label", "fields")} for e in entrances],
                       "values": numbers, "warnings": warnings,
                       "incomplete": incomplete, "unavailable": unavailable})
    return {"id": place.pk, "name": place.name, "region": place.region.code, "routes": routes, "notice": NOTICE}
