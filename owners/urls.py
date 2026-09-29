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
    path("places/<int:pk>/wish/", views.wish_toggle, name="wish"),
    path("support/", views.support, name="support"),
]
