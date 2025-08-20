# outcomes/views.py
from django.db.models import Prefetch, Count, Exists, OuterRef
from django.http import FileResponse, HttpResponseRedirect, Http404
from django.conf import settings
from django.shortcuts import redirect

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Outcome, OutcomeFile
from main.models import Like  # 좋아요 수/상태 재사용
from main.serializers import OutcomeCardSerializer

import io
import os

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def youth_mypage_redirect(request):
    return redirect("outcomes:youth-portfolio") 

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def youth_portfolio(request):
    """
    청년 > 마이페이지 > 포트폴리오
    GET /youth/mypage/portfolio
    현재 로그인한 청년의 Outcome 리스트를 커뮤니티 카드 포맷으로 반환
    """
    profile = getattr(request.user, "profile", None)
    if not profile:
        return Response({"detail": "프로필이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

    cover_qs = OutcomeFile.objects.order_by("order", "id")

    qs = (
        Outcome.objects
        .filter(youth=profile)
        .select_related("mission__request")
        .prefetch_related(Prefetch("files", queryset=cover_qs))
        .only(
            "id", "nopo_pick", "created_at",
            "mission__id", "mission__request__id",
            "mission__request__title",
            "mission__request__store_name",
            "mission__request__category",
        )
        .order_by("-created_at")
        .annotate(like_count=Count("likes", distinct=True))
        .annotate(is_liked=Exists(Like.objects.filter(outcome=OuterRef("pk"), user=profile)))
    )

    for o in qs:
        o._prefetched_cover_files = list(o.files.all()[:1])

    ser = OutcomeCardSerializer(qs, many=True, context={"request": request})
    return Response(ser.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def video_thumb(request, file_id: int):
    """
    영상(OutcomeFile.kind=VIDEO)의 첫 프레임을 JPEG로 반환.
    moviepy / opencv 없거나 실패하면 정적 대체이미지로 리다이렉트.
    """
    try:
        of = OutcomeFile.objects.get(pk=file_id, kind=OutcomeFile.Kind.VIDEO)
    except OutcomeFile.DoesNotExist:
        raise Http404("영상 파일을 찾을 수 없습니다.")

    # 1) moviepy 시도
    try:
        from moviepy.editor import VideoFileClip
        from PIL import Image
        clip = VideoFileClip(of.file.path)
        frame = clip.get_frame(0.1)  # 0.1s
        clip.close()
        buf = io.BytesIO()
        Image.fromarray(frame).save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return FileResponse(buf, content_type="image/jpeg")
    except Exception:
        pass

    # 2) opencv 시도
    try:
        import cv2
        from PIL import Image
        cap = cv2.VideoCapture(of.file.path)
        cap.set(cv2.CAP_PROP_POS_MSEC, 100)
        success, image = cap.read()
        cap.release()
        if success:
            import numpy as np
            img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            return FileResponse(buf, content_type="image/jpeg")
    except Exception:
        pass

    # 3) 실패 → 고정 썸네일
    fallback = getattr(settings, "OUTCOME_VIDEO_FALLBACK_THUMB_STATIC", "static/images/video-thumb-fallback.png")
    return HttpResponseRedirect(fallback)