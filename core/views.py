from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.defaults import page_not_found


def home(request):
    """홈 = 지도 (와이어프레임 1번 '홈 지도 화면')"""
    return redirect("places:map")


def not_found(request, exception):
    """
    404 (config/urls.py handler404). 공개 API(/api/) 주소는 화면이 아니라 JSON으로 답한다.
    예: /api/v1/places/abc/ 처럼 경로 자체가 맞지 않으면 DRF까지 가지 않아 HTML 404가 나가던 문제.
    DEBUG=False(배포·테스트)에서만 쓰인다. DEBUG=True면 Django 디버그 404 화면이 먼저 나온다.
    """
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": "요청한 API 주소를 찾을 수 없습니다."}, status=404)
    return page_not_found(request, exception)


def health(request):
    """배포·모니터링용 헬스체크. DB에 SELECT 1까지 해보고 정상이면 200, 아니면 503."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse(
        {"status": "ok" if db_ok else "error", "db": db_ok},
        status=200 if db_ok else 503,
    )
