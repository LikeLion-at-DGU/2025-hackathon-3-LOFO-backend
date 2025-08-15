from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework import status

from .models import Request
from .serializers import RequestCreateSerializer
from accounts.models import Profile

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
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