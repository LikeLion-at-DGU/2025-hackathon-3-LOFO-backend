from django.urls import reverse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework import status

from .models import Request
from .serializers import RequestCreateSerializer, RequestUpdateSerializer
from accounts.models import Profile


# 상인 홈: 요청작성 링크 + 진행현황 집계 + 최근 요청글 3개 요청
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def nopo_home(request):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return Response({"detail": "프로필이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

    # 상인만 접근 가능
    if profile.role != Profile.Role.MERCHANT:
        raise PermissionDenied("상인만 접근할 수 있습니다.")

    # 내 요청들
    my_qs = Request.objects.filter(owner=profile)

    # 진행현황 집계
    count_open = my_qs.filter(status=Request.Status.OPEN).count()
    count_ongoing = my_qs.filter(status=Request.Status.ONGOING).count()
    count_closed = my_qs.filter(status=Request.Status.CLOSED).count()
    total_count = count_open + count_ongoing + count_closed

    # 최근 3개
    recent_qs = my_qs.order_by("-created_at")[:3]
    recent = []
    for obj in recent_qs:
        image_url = ""
        try:
            if obj.image and hasattr(obj.image, "url"):
                image_url = request.build_absolute_uri(obj.image.url)
        except Exception:
            image_url = ""

        recent.append({
            "id": obj.id,
            "store_name": obj.store_name,
            "title": obj.title,
            "category": obj.category,                    # ex) "PROMO_VIDEO"
            "category_label": obj.get_category_display(),# ex) "홍보영상"
            "status": obj.status,                        # ex) "OPEN"
            "status_label": obj.get_status_display(),    # ex) "모집중"
            "image_url": image_url,
            "url": obj.url,
            "saved_count": obj.saved_count,
            "created_at": obj.created_at,
            "content": obj.content,
        })

    data = {
        "links": {
            "request_create": reverse("nopo-request-create"),  # /nopo/request/create
        },
        "my_progress": {
            "open": count_open,          # 모집중
            "ongoing": count_ongoing,    # 진행중
            "closed": count_closed,      # 종료/중단
            "total": total_count,        # 총요청수
        },
        "my_recent_requests": recent,     # 최신 3개
    }
    return Response(data, status=status.HTTP_200_OK)


# ✅ 요청입력
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def nopo_request_create(request):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return Response({"detail": "프로필이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

    # 무결성 보장용(직접 URL 호출 대비)
    if profile.role != Profile.Role.MERCHANT:
        raise PermissionDenied("상인만 요청을 등록할 수 있습니다.")

    serializer = RequestCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    req = serializer.save(owner=profile, status=Request.Status.OPEN)

    return Response(
        {
            "id": req.id,
            "store_name": req.store_name,
            "url": req.url,
            "category": req.category,
            "title": req.title,
            "content": req.content,
            "status": req.status,
            "saved_count": req.saved_count,
            "created_at": req.created_at,
        },
        status=status.HTTP_201_CREATED,
    )


# ✅ 요청수정
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])   # 이미지 교체 허용
def nopo_request_edit(request, request_id: int):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return Response({"detail": "프로필이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

    req = get_object_or_404(Request, id=request_id)

    if req.owner_id != profile.id:
        raise PermissionDenied("본인만 수정할 수 있습니다.")

    # 모집중일 때만 수정 가능
    if req.status != Request.Status.OPEN:
        return Response({"detail": "모집중 상태에서만 수정할 수 있습니다."}, status=status.HTTP_400_BAD_REQUEST)

    ser = RequestUpdateSerializer(instance=req, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()

    return Response({
        "id": req.id,
        "store_name": req.store_name,
        "url": req.url,
        "category": req.category,
        "title": req.title,
        "content": req.content,
        "status": req.status,
        "saved_count": req.saved_count,
        "created_at": req.created_at,
    }, status=status.HTTP_200_OK)


# ✅ 요청종료
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def nopo_request_end(request, request_id: int):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return Response({"detail": "프로필이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

    req = get_object_or_404(Request, id=request_id)

    if req.owner_id != profile.id:
        raise PermissionDenied("본인 요청만 종료할 수 있습니다.")

    # 모집중일 때만 종료 가능 (추가 조건은 나중에 OR 한 줄만 더 붙이자........^^)
    if req.status != Request.Status.OPEN:
        return Response({"detail": "모집중 상태에서만 종료할 수 있습니다."}, status=status.HTTP_400_BAD_REQUEST)

    req.status = Request.Status.CLOSED
    req.save(update_fields=["status", "updated_at"])

    return Response({"id": req.id, "status": req.status, "message": "요청이 종료/중단 처리되었습니다."}, status=status.HTTP_200_OK)