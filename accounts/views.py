from django.contrib.auth.models import User
from django.contrib.auth import login
from django.db import transaction, IntegrityError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import Profile
from .serializers import LoginSerializer

DJANGO_BACKEND = "django.contrib.auth.backends.ModelBackend"

def _handle_login(request, role):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    phone_num = serializer.validated_data["phone_num"]
    nickname = serializer.validated_data.get("nickname", "").strip()

    try:
        profile = Profile.objects.select_related("user").get(phone_num=phone_num, role=role)
        user = profile.user
        login(request, user, backend=DJANGO_BACKEND)
        home_url = "/youth/home" if role == Profile.Role.YOUTH else "/nopo/home"
        return Response({"message": "기존 회원 로그인 성공", "redirect": home_url}, status=status.HTTP_200_OK)

    except Profile.DoesNotExist:
        if not nickname:
            return Response({"detail": "신규 회원은 닉네임이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 닉네임 중복 사전 체크
        if Profile.objects.filter(nickname=nickname).exists():
            return Response({"detail": "이미 사용 중인 닉네임입니다."}, status=status.HTTP_409_CONFLICT)
        
        try:
            with transaction.atomic():
                user = User.objects.create(username=f"{role.lower()}_{phone_num}")
                user.set_unusable_password()
                user.save()

                Profile.objects.create(
                    user=user,
                    phone_num=phone_num,
                    nickname=nickname,
                    role=role
                )

            login(request, user, backend=DJANGO_BACKEND)
        except IntegrityError:
            # 혹시 동시에 같은 닉네임으로 가입 시도하면 DB에서 막히므로 처리
            return Response({"detail": "이미 사용 중인 닉네임입니다."}, status=status.HTTP_409_CONFLICT)
        
        home_url = "/youth/home" if role == Profile.Role.YOUTH else "/nopo/home"
        return Response({"message": "신규 회원 가입 및 로그인 성공", "redirect": home_url}, status=status.HTTP_201_CREATED)

@api_view(["POST"])
@permission_classes([AllowAny])  
def login_youth(request):
    return _handle_login(request, Profile.Role.YOUTH)

@api_view(["POST"])
@permission_classes([AllowAny])
def login_nopo(request):
    return _handle_login(request, Profile.Role.MERCHANT)