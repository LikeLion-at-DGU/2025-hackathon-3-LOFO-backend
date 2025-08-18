from django.urls import path
from . import views

urlpatterns = [
     path('comunity', views.comunity, name = 'comunity')
]