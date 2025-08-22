from django.urls import path
from .views import *

urlpatterns = [
     path('home', home, name='home'),
     path('home/ai-mission', home_ai, name = 'home-ai-mission'),
     path('mission/<int:id>', mission_detail, name ='mission-detail'),
     path('home/save-mission', save_mission, name='save-mission'),
     path("plan", generate_plan, name="generate_plan"),
     path('mission', mission, name='mission'),
     path('mission/done', mission_done, name='mission-done'),
     path("mission/submit", mission_submit, name="mission_submit"),
     path('mymission', my_mission, name='mymission'),
     ]