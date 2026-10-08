from django.urls import path

from . import api, mobility_api
from accounts.mobility_api import preferences

app_name = "api"

urlpatterns = [
    path("mobility/", mobility_api.settings_catalogue, name="mobility-catalogue"),
    path("mobility/preferences/", preferences, name="mobility-preferences"),
    path("mobility/places/", mobility_api.evaluate, name="mobility-evaluate"),
    path("meta/", api.meta, name="meta"),
    path("places/", api.place_list, name="place-list"),
    path("places/<int:pk>/", api.place_detail_api, name="place-detail"),
    path("places.geojson", api.places_geojson, name="places-geojson"),
]
