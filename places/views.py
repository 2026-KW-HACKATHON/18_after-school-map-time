from django.shortcuts import get_object_or_404, render

from judgments.models import ConditionProfile, Judgment

from .models import Place, Region
from .selectors import judgment_payload, place_detail, place_summary, unknown_payload

SEARCH_LIMIT = 30


def _region():
    return Region.objects.filter(is_active=True).order_by("id").first()


def map_page(request):
    """홈 = 지도 (와이어프레임 1~3·6번: 지도, 조건 맞는 장소 없음, 마커 팝업, 지도 오류)"""
    return render(request, "places/map.html", {"region": _region()})


def search_page(request):
    """
    장소명 검색 (와이어프레임 4·5번). 이름으로 찾는 기능이라 판정과 상관없이 보여준다.
    정렬은 이름순 — 접근성 낮은 순 정렬은 만들지 않는다 (기획 v2 3.2)
    """
    region = _region()
    q = request.GET.get("q", "").strip()
    profiles = list(ConditionProfile.objects.filter(is_active=True))
    profile = next((p for p in profiles if p.key == request.GET.get("profile")), profiles[0] if profiles else None)

    results = []
    if q and region:
        places = list(
            Place.objects.in_region(region).filter(is_closed=False, name__icontains=q).order_by("name")[:SEARCH_LIMIT]
        )
        judgments = {}
        if profile:
            judgments = {
                j.place_id: j
                for j in Judgment.objects.filter(place__in=places, profile=profile).select_related("matched_rule")
            }
        for place in places:
            results.append({
                "place": place,
                "judgment": judgment_payload(judgments.get(place.id)) or unknown_payload(),
                **place_summary(place),
            })

    return render(request, "places/search.html", {
        "q": q, "results": results, "profiles": profiles, "profile": profile, "searched": bool(q),
    })


def detail_page(request, pk):
    """장소 상세 (와이어프레임 7번)"""
    place = get_object_or_404(Place.objects.select_related("building", "region"), pk=pk, is_closed=False)
    return render(request, "places/detail.html", place_detail(place))
