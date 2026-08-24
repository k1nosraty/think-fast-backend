"""Project and operational routes. Product routes begin in T2."""

from django.contrib import admin
from django.urls import path

from config.health import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
