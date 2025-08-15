from django.urls import path
from . import views

urlpatterns = [
    path("nopo/home/request", views.nopo_request_create, name="nopo-request-create"),
]