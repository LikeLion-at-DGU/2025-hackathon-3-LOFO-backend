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
from missions.models import Mission
from inquiries.models import NopoFeedback, Saved, Request
from main.serializers import OutcomeCardSerializer

import io
import os

@api_view(["GET"])
def youth_mypage_redirect(request):
    return redirect("outcomes:youth-portfolio") 

# 청년 마이페이지 > 포트폴리오
@api_view(["GET"])
def youth_portfolio(request):

    # 청년 > 마이페이지 > 포트폴리오
    # GET /youth/mypage/portfolio
    # 현재 로그인한 청년의 Outcome 리스트를 커뮤니티 카드 포맷으로 반환
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


#동영상 처리.. 추후 코드 수정 필요
@api_view(["GET"])
def video_thumb(request, file_id: int):

    # 영상(OutcomeFile.kind=VIDEO)의 첫 프레임을 JPEG로 반환.
    # moviepy / opencv 없거나 실패하면 정적 대체이미지로 리다이렉트.
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

# 청년 마이페이지 > 성장지표 > 피드백
@api_view(["GET"])
def youth_insights(request):
    profile = request.user.profile  

    # 미션 통계
    done_cnt = Mission.objects.filter(youth=profile, status=Mission.Status.DONE).count()
    ing_cnt = Mission.objects.filter(youth=profile, status=Mission.Status.IN_PROGRESS).count()
    nopo_pick_cnt = Outcome.objects.filter(youth=profile, nopo_pick=True).count()
    total_cnt = done_cnt + ing_cnt

    # 8~9. 내가 받은 모든 피드백 목록 (가게이름 | 코멘트 44자 요약)
    fb_qs = (
        NopoFeedback.objects
        .filter(outcome__youth=profile)
        .select_related("outcome__mission__request")
        .order_by("-created_at")
    )
    feedbacks = []
    for fb in fb_qs:
        store = fb.outcome.mission.request.store_name
        comment = fb.comment
        line = f"{store} | {comment}"
        if len(line) > 44:   # 44자 제한
            line = line[:43] + "…"

        feedbacks.append({
            "outcome_id": fb.outcome_id,   # 클릭 시 /outcomes/feedback/<outcome_id>
            "store_name": store,
            "comment": comment,
            "summary_44": line,
            "created_at": fb.created_at,
        })
    feedback_cnt = fb_qs.count()

    # 노포픽 작품
    cover_qs = OutcomeFile.objects.order_by("order", "id")
    pick_qs = (
        Outcome.objects
        .filter(youth=profile, nopo_pick=True)
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
    for o in pick_qs:
        o._prefetched_cover_files = list(o.files.all()[:1])  # 카드 썸네일 1장

    pick_ser = OutcomeCardSerializer(pick_qs, many=True, context={"request": request})

    data = {
        # 로고/닉네임/전화번호
        "logo_url": "/static/images/lofo-logo.png",
        "nickname": getattr(profile, "nickname", ""),
        "phone_num": getattr(profile, "phone_num", ""),

        # 수치
        "stats": {
            "missions_done": done_cnt,
            "missions_in_progress": ing_cnt,
            "nopo_pick_count": nopo_pick_cnt,
            "missions_total": total_cnt,
            "feedback_count": feedback_cnt,
        },

        # 피드백 리스트
        "feedbacks": feedbacks,

        # 노포픽 작품
        "nopo_pick_outcomes": pick_ser.data,
    }
    return Response(data, status=200)

# 청년 마이페이지 > 성장지표 > 피드백 detail
@api_view(["GET"])
def outcome_feedback_detail(request, outcome_id: int):

    # Outcome 존재 확인(방어적)
    try:
        Outcome.objects.only("id").get(pk=outcome_id)
    except Outcome.DoesNotExist:
        return Response({"detail": "존재하지 않는 결과물입니다."}, status=status.HTTP_404_NOT_FOUND)

    fb = NopoFeedback.objects.filter(outcome_id=outcome_id).select_related("author").first()
    if not fb:
        return Response({"detail": "아직 상인 피드백이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

    # 코드값 + 라벨 둘 다 내려줌 
    data = {
        "id": fb.id,
        "outcome_id": outcome_id,
        "author_id": fb.author_id,
        "overall_satisfaction": {
            "value": fb.overall_satisfaction,
            "label": fb.get_overall_satisfaction_display(),
        },
        "reflection_level": {
            "value": fb.reflection_level,
            "label": fb.get_reflection_level_display(),
        },
        "practical_use": {
            "value": fb.practical_use,
            "label": fb.get_practical_use_display(),
        },
        "comment": fb.comment,
        "created_at": fb.created_at,
    }
    return Response(data, status=status.HTTP_200_OK)

# 청년 마이페이지 > 내활동
@api_view(["GET"])
def youth_saved(request):
    profile = request.user.profile  

    # 찜한 요청: 개수 + 전체 목록
    saved_qs = (
        Saved.objects
        .filter(user=profile)
        .select_related("request")
        .order_by("-created_at")
    )
    saved_count = saved_qs.count()

    saved_requests = []
    for s in saved_qs:
        r: Request = s.request
        url_attr = getattr(getattr(r, "image", None), "url", None)
        image_url = request.build_absolute_uri(url_attr) if url_attr else ""
        saved_requests.append({
            "id": r.id,
            "store_name": r.store_name,
            "title": r.title,
            "category": r.category,
            "category_label": r.get_category_display(),
            "status": r.status,
            "status_label": r.get_status_display(),
            "image_url": image_url,
            "saved_count": r.saved_count,
            "created_at": r.created_at,
        })

    # 커뮤니티에서 좋아요한 작품: 개수 + 전체 목록
    cover_qs = OutcomeFile.objects.order_by("order", "id")
    liked_qs = (
        Outcome.objects
        .filter(likes__user=profile)
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
        .distinct()
    )
    for o in liked_qs:
        o._prefetched_cover_files = list(o.files.all()[:1])

    liked_ser = OutcomeCardSerializer(liked_qs, many=True, context={"request": request})

    return Response({
        "saved_requests_count": saved_count,
        "saved_requests": saved_requests,          # 전체 리스트
        "liked_outcomes_count": liked_qs.count(),
        "liked_outcomes": liked_ser.data,          # 전체 리스트
    }, status=200)