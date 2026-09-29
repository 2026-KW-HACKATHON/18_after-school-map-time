from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("api/v1/", include("places.api_urls")),     # 공개 읽기 API
    # 로그인·로그아웃·카카오 콜백 (/accounts/kakao/login/callback/)
    path("accounts/", include("allauth.urls")),
    # 새 앱을 만들면 여기에 추가: path("reports/", include("reports.urls")),
]

# 개발(DEBUG=True) 중 업로드 파일(media) 서빙. 배포에서는 nginx가 /media/를 직접 서빙
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
