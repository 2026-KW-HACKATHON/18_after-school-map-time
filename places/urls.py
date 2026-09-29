from django.urls import path

from . import views

app_name = "places"

urlpatterns = [
    path("map/", views.map_page, name="map"),
    path("places/<int:pk>/", views.detail_page, name="detail"),
]
