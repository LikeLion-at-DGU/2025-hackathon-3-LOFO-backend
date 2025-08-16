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