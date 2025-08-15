from django.urls import path
from .views import *

urlpatterns = [
     path('mission-list', mission_list, name='mission-list'),
     path('mission/<int:id>', mission_detail, name ='mission-detail'),
]