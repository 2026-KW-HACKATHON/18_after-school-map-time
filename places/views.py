from django.shortcuts import get_object_or_404, render
from django.db.models import Q
from django.core.paginator import Paginator
from urllib.parse import urlencode
from django.utils import timezone

from judgments.models import ConditionProfile, Judgment

from .models import Place, Region
from .selectors import judgment_payload, place_detail, place_summary, unknown_payload

SEARCH_LIMIT = 30
SEARCH_CATEGORIES = [("", "전체"), ("CAFE", "카페"), ("RESTAURANT", "음식점"), ("LIFE", "생활")]


def search_places(region, query, category=""):
    places = Place.objects.in_region(region).filter(is_closed=False)
    places = places.filter(Q(name__icontains=query) | Q(address__icontains=query))
    if category == "LIFE":
        places = places.exclude(category__in=[Place.Category.CAFE, Place.Category.RESTAURANT])
    elif category:
        places = places.filter(category=category)
    return places.order_by("name", "pk")


def paginated_search(region, query, category="", page=1):
    """공용 검색 범위/정렬 유지. 빈 검색어도 30곳씩 전부 탐색할 수 있게 한다."""
    return Paginator(search_places(region, query, category), SEARCH_LIMIT).get_page(page)


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
    q = request.GET.get("q", "").replace("\x00", "").strip()  # NUL 문자는 PostgreSQL이 거부 → 500 방지
    profiles = list(ConditionProfile.objects.filter(is_active=True))
    profile = next((p for p in profiles if p.key == request.GET.get("profile")), profiles[0] if profiles else None)
    category = request.GET.get("category", "")
    if category not in dict(SEARCH_CATEGORIES):
        category = ""

    results = []
    page_obj = None
    if region:
        from core.validation import parse_pk
        page_obj = paginated_search(region, q, category, parse_pk(request.GET.get("page", "1")) or 1)
        places = list(page_obj.object_list)
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
        "q": q, "results": results, "profiles": profiles, "profile": profile, "searched": region is not None,
        "region": region,
        "category": category, "categories": SEARCH_CATEGORIES,
        "page_obj": page_obj,
        "pagination_query": urlencode({"q": q, "category": category, "profile": profile.key if profile else ""}),
    })


def _record_view(request, place):
    """
    조건별 조회 수 (사장님 대시보드용, 기획 v2 4.5). 지도·검색에서 넘어올 때 붙는 ?profile= 로 센다.
    같은 사람이 같은 날 새로고침해도 한 번만 (세션에 기록). 누가 봤는지는 저장하지 않는다.
    """
    from owners.models import PlaceViewStat

    profile = ConditionProfile.objects.filter(key=request.GET.get("profile", ""), is_active=True).first()
    if profile is None:
        return
    key = f"viewed:{place.pk}:{profile.key}:{timezone.localdate().isoformat()}"
    if request.session.get(key):
        return
    request.session[key] = True
    PlaceViewStat.record(place, profile)


def detail_page(request, pk):
    """장소 상세 (와이어프레임 7번 + 사장님 정보)"""
    from owners.models import OwnerClaim, OwnerResponse, VisitWish

    place = get_object_or_404(Place.objects.select_related("building", "region"), pk=pk, is_closed=False)
    _record_view(request, place)
    context = place_detail(place)
    context["owner_response"] = OwnerResponse.objects.filter(place=place).first()
    context["is_owner"] = OwnerClaim.is_owner(request.user, place)
    context["wished"] = set(
        VisitWish.objects.filter(user=request.user, place=place).values_list("profile_id", flat=True)
    ) if request.user.is_authenticated else set()
    return render(request, "places/detail.html", context)
