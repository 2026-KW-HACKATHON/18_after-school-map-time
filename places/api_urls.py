from django.urls import path

from . import api

app_name = "api"

urlpatterns = [
    path("meta/", api.meta, name="meta"),
    path("places/", api.place_list, name="place-list"),
    path("places/<int:pk>/", api.place_detail_api, name="place-detail"),
    path("places.geojson", api.places_geojson, name="places-geojson"),
]
