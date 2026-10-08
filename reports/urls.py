from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("report/new/", views.report_new, name="new"),
    path("report/done/", views.report_done, name="done"),
    path("report/ai-prefill/", views.ai_prefill, name="ai-prefill"),  # 제보 작성 중 'AI로 항목 채우기' (JSON)
    path("report/photo-preview/", views.photo_preview, name="photo-preview"),
    path("reports/<int:pk>/confirm/", views.report_confirm, name="confirm"),
    path("places/<int:pk>/reconfirm/", views.place_reconfirm, name="reconfirm"),
    path("entrances/<int:pk>/photo-fix/", views.photo_fix_request, name="photo-fix"),
]
