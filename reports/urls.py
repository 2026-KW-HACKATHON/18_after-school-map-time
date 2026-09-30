from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("report/new/", views.report_new, name="new"),
    path("report/done/", views.report_done, name="done"),
    path("reports/<int:pk>/confirm/", views.report_confirm, name="confirm"),
    path("places/<int:pk>/reconfirm/", views.place_reconfirm, name="reconfirm"),
]
