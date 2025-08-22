from django.urls import path
from . import views

urlpatterns = [
    path("request", views.nopo_request, name="nopo-request"),
    path("request/create", views.nopo_request_create, name="nopo-request-create"),
    path("request/<int:request_id>/edit", views.nopo_request_edit, name="nopo-request-edit"), 
    path("request/<int:request_id>/end", views.nopo_request_end, name="nopo-request-end"), 

    path("home", views.nopo_home, name="nopo-home"), # 상인홈

    path("received", views.nopo_received, name="nopo-received"), #상인 마이페이지
    path("received/feedback", views.nopo_received_feedback, name="nopo-received-feedback"),
    path("received/<int:outcome_id>/form-data", views.nopo_feedback_form_data, name="nopo-feedback-form-data"),
    path("received/<int:outcome_id>/download", views.nopo_received_download, name="nopo-received-download"),
]