from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from inquiries.models import Request
from .serializers import RequestListSerializer

# Create your views here.

@api_view(['GET'])
def mission_list(request):
     missions = Request.objects.all().order_by('-id')  # 최신순
     serializer = RequestListSerializer(missions, many=True)
     return Response(serializer.data)


@api_view(["GET"])
def mission_detail(request, id):
     try:
          req = Request.objects.get(pk=id)
     except Request.DoesNotExist:
          return Response({"detail": "존재하지 않는 요청입니다."}, status= status.HTTP_404_NOT_FOUND)

     serializer = RequestListSerializer(req)
     return Response(serializer.data, status=status.HTTP_200_OK)