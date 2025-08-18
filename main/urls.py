from django.urls import path
from . import views

urlpatterns = [
     path('comunity/', views.comunity, name = 'comunity'),
     path('comunity/<int:id>/like', views.like_toggle,name = 'like')
]