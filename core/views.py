from django.db import connection
from django.http import JsonResponse


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
