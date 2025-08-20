from django.urls import path
from . import views

app_name = "outcomes"

urlpatterns = [
    path("mypage", views.youth_mypage_redirect, name="youth-mypage-redirect"),
    path("mypage/portfolio", views.youth_portfolio, name="youth-portfolio"),
    path("files/<int:file_id>/video-thumb", views.video_thumb, name="video-thumb"), #영상 썸네일
    path("feedback/<int:outcome_id>", views.outcome_feedback_detail, name="outcome-feedback-detail"), #피드백 확인
]