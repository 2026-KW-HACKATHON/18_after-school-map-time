"""기존 읽기 API는 유지하고 개인화된 파생 판정을 별도 POST 요청으로 계산한다."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from accounts.mobility_api import has_consent, restored_settings
from core.validation import parse_pk
from judgments.constants import display
from judgments.engine import judge_profiles, load_rules
from judgments.mobility import NOTICE, catalogue, merged_constraints, normalize_settings, requirements
from judgments.models import RuleSet
from .api import _place_brief
from .models import Place, Region


@api_view(["GET"])
@permission_classes([AllowAny])
def settings_catalogue(request):
    settings, warning = restored_settings(request.user)
    response = Response({**catalogue(), "authenticated": request.user.is_authenticated,
                         "consented": has_consent(request.user), "settings": settings, "warning": warning})
    response["Cache-Control"] = "private, no-store"
    return response


@api_view(["GET"])
@permission_classes([AllowAny])
def reference(request, pk):
    parsed = parse_pk(pk)
    if parsed is None:
        return Response({"detail": "장소 ID는 ASCII 양의 정수로 입력해 주세요."}, status=400)
    place = get_object_or_404(Place.objects.select_related("building", "region"), pk=parsed,
                              is_closed=False, region__is_active=True)
    from judgments.place_reference import place_reference
    response = Response(place_reference(place))
    response["Cache-Control"] = "private, no-store"
    return response


class EvaluateThrottle(SimpleRateThrottle):
    """
    개인화 판정은 요청마다 지역의 모든 장소를 다시 계산하므로(공용 판정 캐시를 쓰지 않음) 반복 요청을 제한한다.
      - 기준: 로그인 회원은 회원별, 비로그인은 IP별
      - 넉넉하게 잡은 이유: 전시장처럼 여러 사람이 같은 와이파이(같은 IP)로 접속할 수 있음
      - 기록은 Django 기본 캐시(gunicorn 프로세스별 메모리)에 남는다 → 프로세스가 여럿이면 실제 허용량은 그만큼 늘어남
    """
    scope = "mobility_evaluate"
    rate = "120/min"

    def get_cache_key(self, request, view):
        ident = f"user-{request.user.pk}" if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


@api_view(["POST"])
@permission_classes([AllowAny])
def evaluate(request):
    # 설정값을 URL·공용 판정 캐시에 남기지 않는다. POST는 계산만 하고 DB에는 저장하지 않는다.
    throttle = EvaluateThrottle()
    if not throttle.allow_request(request, None):
        wait = throttle.wait()
        response = Response({"detail": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."}, status=429)
        if wait:
            response["Retry-After"] = str(int(wait) + 1)
        return response
    try:
        if not isinstance(request.data, dict) or set(request.data) - {"settings", "region", "all", "q", "place_ids", "category"}:
            raise DjangoValidationError("장소 판정의 입력 형식을 확인해 주세요.")
        settings = normalize_settings(request.data.get("settings"))
        region_code = request.data.get("region")
        if region_code is not None and not isinstance(region_code, str):
            raise DjangoValidationError("지역을 확인해 주세요.")
        regions = Region.objects.filter(is_active=True)
        region = get_object_or_404(regions, code=region_code) if region_code else regions.order_by("id").first()
        if region is None:
            return Response({"detail": "지역을 찾을 수 없습니다."}, status=404)
        query = request.data.get("q")
        if query is not None and (not isinstance(query, str) or len(query) > 200 or "\x00" in query):
            raise DjangoValidationError("검색어를 확인해 주세요.")
        from .views import SEARCH_CATEGORIES, SEARCH_LIMIT, search_places
        category = request.data.get("category", "")
        if not isinstance(category, str) or category not in dict(SEARCH_CATEGORIES) or (category and query is None):
            raise DjangoValidationError("검색 업종을 확인해 주세요.")
        show_all = request.data.get("all", True)
        if type(show_all) is not bool:
            raise DjangoValidationError("표시 조건을 확인해 주세요.")
        places = Place.objects.in_region(region).filter(is_closed=False).select_related("building").prefetch_related("entrances", "building__entrances").order_by("name")
        if query is not None:
            places = search_places(region, query.strip(), category).select_related("building").prefetch_related("entrances", "building__entrances")[:SEARCH_LIMIT] if query.strip() else places.none()
        ids = request.data.get("place_ids")
        if ids is not None:
            if query is not None or not isinstance(ids, list) or not ids:
                raise DjangoValidationError("장소 ID를 확인해 주세요.")
            parsed = [parse_pk(str(i) if type(i) is int else i) for i in ids]
            if any(i is None for i in parsed):
                raise DjangoValidationError("장소 ID는 ASCII 양의 정수로 입력해 주세요.")
            places = places.filter(pk__in=parsed)
            if places.count() != len(set(parsed)):
                return Response({"detail": "장소를 찾을 수 없습니다."}, status=404)
    except DjangoValidationError as error:
        return Response({"detail": " ".join(error.messages)}, status=400)

    people = requirements(settings)
    rule_set = RuleSet.active()
    all_rules = load_rules(rule_set) if rule_set else None  # 장소마다 규칙을 다시 읽지 않도록 한 번만
    results = []
    for place in places:
        result = judge_profiles(place, people, rule_set=rule_set, all_rules=all_rules)
        payload = {**display(result.outcome), "reason": result.reason, "improved": False,
                   "rule_version": rule_set.version if rule_set else None, "basis": "PERSONAL",
                   "basis_label": "내 이동 조건", "explanation": result.reason or "입력한 조건과 검증된 장소 정보로 안내해요.",
                   "personalized": True}
        if show_all or not payload["hidden_by_default"]:
            row = {**_place_brief(place), "judgment": payload}
            if query is not None:
                from .selectors import place_summary
                summary = place_summary(place)
                row.update(facts=summary["facts"], last_checked=summary["last_checked"].isoformat() if summary["last_checked"] else None)
            results.append(row)
    response = Response({"region": region.code, "count": len(results), "results": results,
                         "constraints": merged_constraints(settings), "notice": NOTICE,
                         "preferences": ["휴식 좌석 데이터 수집이 필요해요."] if any(settings["overrides"].get(k, {}).get("prefers_rest_seat") for k in settings["selected"]) else []})
    response["Cache-Control"] = "private, no-store"
    return response
