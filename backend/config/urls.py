from django.urls import path

from api.routes import api

urlpatterns = [path("api/", api.urls)]
