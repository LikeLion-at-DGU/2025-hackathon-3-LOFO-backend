from django.urls import path
from . import views

urlpatterns = [
    path("auth/login-youth", views.login_youth, name="login-youth"),
    path("auth/login-nopo", views.login_nopo, name="login-nopo"),
]