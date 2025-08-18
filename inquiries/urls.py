from django.urls import path
from . import views

urlpatterns = [
    path("request/create", views.nopo_request_create, name="nopo-request-create"),
    path("request/<int:request_id>/edit", views.nopo_request_edit, name="nopo-request-edit"), 
    path("request/<int:request_id>/end", views.nopo_request_end, name="nopo-request-end"),    
]