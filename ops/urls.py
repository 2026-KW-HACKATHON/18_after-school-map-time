from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("login/", views.OpsLoginView.as_view(), name="login"),
    path("", views.dashboard, name="dashboard"),
    path("reports/", views.report_list, name="reports"),
    path("reports/<int:pk>/", views.report_review, name="report-review"),
    path("reports/<int:pk>/done/", views.report_done, name="report-done"),
    path("places/", views.place_list, name="places"),
    path("places/new/", views.place_edit, name="place-new"),
    path("places/<int:pk>/edit/", views.place_edit, name="place-edit"),
    path("places/<int:pk>/delete/", views.place_delete, name="place-delete"),
    path("places/<int:pk>/saved/", views.place_saved, name="place-saved"),
    path("places/<int:pk>/claim-code/", views.issue_claim_code, name="claim-code"),
    path("claims/", views.claim_list, name="claims"),
]
