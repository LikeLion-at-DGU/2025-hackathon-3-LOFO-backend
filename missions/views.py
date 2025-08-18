from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from inquiries.models import Request, AiRequest, Saved
from .serializers import RequestListSerializer, AiRequestListSerializer

# 청년 홈: 상인 요청 리스트
@api_view(["GET"])
def home(request): 
     category = request.GET.get("category")
     sort = request.GET.get("sort", "latest")  # 정렬 기준 기본 - 최신순

     qs = Request.objects.filter(status="OPEN") # status = open 인 것만
     if category:
          qs = qs.filter(category=category)

     if sort == "popular":  # 찜 많은 순
          qs = qs.order_by("-saved_count")
     else:
          qs = qs.order_by("-created_at")

     serializer = RequestListSerializer(qs, many=True)
     return Response(serializer.data, status=status.HTTP_200_OK)


# 청년 홈2: ai 요청 리스트
@api_view(["GET"])
def home_ai(request):
     category = request.GET.get("category")
     sort = request.GET.get("sort", "latest")

     qs = AiRequest.objects.filter(status="IN_PROGRESS") # status
     if category:
          qs = qs.filter(category=category)

     if sort == "popular":  # 찜 많은 순
          qs = qs.order_by("-saved_count")
     else:  # 최신순
          qs = qs.order_by("-created_at")

     serializer = AiRequestListSerializer(qs, many=True)
     return Response(serializer.data, status=status.HTTP_200_OK)



@api_view(["GET"])
def mission_detail(request, id):
     try:
          req = Request.objects.get(pk=id)
     except Request.DoesNotExist:
          return Response({"detail": "존재하지 않는 요청입니다."}, status= status.HTTP_404_NOT_FOUND)

     serializer = RequestListSerializer(req)
     return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_mission(request):
     req_id = request.data.get("request_id")
     if not req_id:
          return Response({"detail": "request_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

     req = get_object_or_404(Request, pk=req_id)
     profile = request.user.profile

     saved_obj, created = Saved.objects.get_or_create(user=profile, request=req)
     if not created:
          saved_obj.delete()
          is_saved = False
     else:
          is_saved = True

     # 시그널로 saved_count 업데이트 → 최신값 응답
     req.refresh_from_db(fields=["saved_count"])

     return Response(
          {"id": req.id, "is_saved": is_saved, "saved_count": req.saved_count},
          status=status.HTTP_200_OK,
     )