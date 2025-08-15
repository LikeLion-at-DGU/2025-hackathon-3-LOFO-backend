from django.urls import path
from . import views

urlpatterns = [
    path("login-youth", views.login_youth, name="login-youth"),
    path("login-nopo", views.login_nopo, name="login-nopo"),
]