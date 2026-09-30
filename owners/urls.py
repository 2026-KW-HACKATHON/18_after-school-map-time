from django.urls import path

from . import views

app_name = "owners"

urlpatterns = [
    path("owner/", views.home, name="home"),
    path("owner/claim/", views.claim, name="claim"),
    path("owner/places/<int:pk>/", views.dashboard, name="dashboard"),
    path("owner/places/<int:pk>/response/", views.response_edit, name="response"),
    path("owner/places/<int:pk>/declaration/", views.declaration, name="declaration"),
    path("owner/places/<int:pk>/correction/", views.correction, name="correction"),
    path("owner/places/<int:pk>/photo/", views.photo_request, name="photo"),
    path("owner/buildings/<int:pk>/", views.building_dashboard, name="building"),
    path("owner/buildings/<int:pk>/correction/", views.building_correction, name="building-correction"),
    path("buildings/<int:pk>/improve/", views.building_improve, name="building-improve"),
    path("places/<int:pk>/wish/", views.wish_toggle, name="wish"),
    path("wishes/", views.wishes, name="wishes"),
    path("support/", views.support, name="support"),
]
