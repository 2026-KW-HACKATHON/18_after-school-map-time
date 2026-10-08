"""
공개 읽기 API /api/v1/ (기획 v2 8장 — 지도 화면이 쓰고, 구청 등 외부에도 열 수 있는 읽기 전용 API)

GET /api/v1/meta/?region=wolgye1                        지역 정보, 이동 조건 목록, 표시 정책
GET /api/v1/places/?region=wolgye1&profile=WHEELCHAIR   지도용 목록 (기본: 어려움·미확인 숨김, &all=1 이면 모두)
GET /api/v1/places/<id>/                                장소 상세 (건물 공용 / 가게 섹션)
GET /api/v1/places.geojson?region=wolgye1               GeoJSON 내보내기 (전체 이동 조건 판정 포함)
"""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from judgments.constants import DISPLAY
from judgments.models import ConditionProfile, Judgment

from .models import Place, Region
from .selectors import judgment_payload, map_places, place_detail


def _region(request):
    code = request.query_params.get("region")
    regions = Region.objects.filter(is_active=True)
    region = regions.filter(code=code).first() if code else regions.order_by("id").first()
    if region is None:
        raise NotFound("지역을 찾을 수 없습니다.")
    return region


def _profile(request):
    key = request.query_params.get("profile")
    if not key:
        return None
    profile = ConditionProfile.objects.filter(key=key, is_active=True).first()
    if profile is None:
        raise ValidationError({"profile": f"알 수 없는 이동 조건입니다: {key}"})
    return profile


def _place_brief(place):
    return {
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "category_label": place.get_category_display(),
        "address": place.address,
        "lat": float(place.lat),
        "lng": float(place.lng),
        "floor": place.floor,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def meta(request):
    region = _region(request)
    from .boundaries import region_boundary, region_boundary_layers
    return Response({
        "region": {
            "code": region.code,
            "name": region.name,
            "center": {"lat": float(region.center_lat), "lng": float(region.center_lng)},
            "map_level": region.map_level,
            "boundary": region_boundary(region),
            "boundary_layers": region_boundary_layers(region),
        },
        "profiles": [{"key": p.key, "label": p.label} for p in ConditionProfile.objects.filter(is_active=True)],
        "display": {code: info for code, info in DISPLAY.items()},
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def place_list(request):
    region = _region(request)
    profile = _profile(request)
    show_all = request.query_params.get("all") in ("1", "true")
    rows = map_places(region, profile, show_all)
    return Response({
        "region": region.code,
        "profile": profile.key if profile else None,
        "count": len(rows),
        "results": [{**_place_brief(r["place"]), "judgment": r["judgment"]} for r in rows],
    })


def _section_json(section):
    if section is None:
        return None
    out = {
        "entrances": [
            {**{k: e[k] for k in ("id", "name", "is_main", "description")},
             "photo_url": e["photo"].url if e["photo"] else None,
             "fields": _fields_json(e["fields"])}
            for e in section["entrances"]
        ],
        "fields": _fields_json(section["fields"]),
        "facilities": [
            {**{k: f[k] for k in ("id", "name", "kind", "kind_label", "description", "location_text")},
             "lat": float(f["lat"]) if f["lat"] is not None else None,
             "lng": float(f["lng"]) if f["lng"] is not None else None,
             "checked_at": f["checked_at"].isoformat(),
             "photo_url": f["photo"].url if f["photo"] else None,
             "fields": _fields_json(f["fields"])}
            for f in section["facilities"]
        ],
        "facility_counts": section["facility_counts"],
    }
    if "building" in section:
        b = section["building"]
        out["building"] = {"id": b.id, "name": b.name, "address": b.address}
    return out


def _fields_json(fields):
    return [
        {**{k: f[k] for k in ("key", "label", "value", "unit", "pending")},
         "checked_at": f["checked_at"].isoformat() if f["checked_at"] else None}
        for f in fields
    ]


@api_view(["GET"])
@permission_classes([AllowAny])
def place_detail_api(request, pk):
    place = get_object_or_404(Place.objects.select_related("building", "region"), pk=pk, is_closed=False)
    d = place_detail(place)
    return Response({
        **_place_brief(place),
        "region": place.region.code,
        "judgments": [{"profile": j["profile"].key, "profile_label": j["profile"].label, **j["judgment"]}
                      for j in d["judgments"]],
        "building": _section_json(d["building"]),
        "place": _section_json(d["place_section"]),
        "last_checked": d["last_checked"].isoformat() if d["last_checked"] else None,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def places_geojson(request):
    """GeoJSON FeatureCollection. 판정은 이동 조건별 결과 코드와 문구 (순위·점수 없음, 기획 v2 OP-1)"""
    region = _region(request)
    places = list(Place.objects.in_region(region).filter(is_closed=False).order_by("id"))
    judgments = {}
    for j in Judgment.objects.filter(place__in=places).select_related("profile"):
        judgments.setdefault(j.place_id, {})[j.profile_id] = judgment_payload(j)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(p.lng), float(p.lat)]},  # GeoJSON은 [경도, 위도]
            "properties": {
                **{k: v for k, v in _place_brief(p).items() if k not in ("lat", "lng")},
                "judgments": {
                    key: {"code": j["code"], "label": j["label"], "reason": j["reason"]}
                    for key, j in judgments.get(p.id, {}).items()
                },
            },
        }
        for p in places
    ]
    response = Response({"type": "FeatureCollection", "features": features})
    response["Content-Disposition"] = f'inline; filename="teokeopne-{region.code}.geojson"'
    return response
