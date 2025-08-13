from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction, IntegrityError
from .models import Profile
from .serializers import LoginSerializer

def _login(request, role_value, redirect_url):
    s = LoginSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    phone = s.validated_data["phone_num"]
    nickname = s.validated_data.get("nickname")

    try:
        prof = Profile.objects.get(phone_num=phone)
        if prof.role != role_value:
            return Response(
                {"detail": "이미 다른 유형으로 가입된 번호입니다.", "registered_role": prof.role},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"status": "OK", "role": prof.role, "profile_id": prof.id, "redirect_url": redirect_url},
            status=status.HTTP_200_OK,
        )
    except Profile.DoesNotExist:
        if not nickname:
            return Response(
                {"status": "NEED_SIGNUP", "next": "NEED_NICKNAME"},
                status=status.HTTP_202_ACCEPTED,
            )
        try:
            with transaction.atomic():
                prof = Profile.objects.create(
                    phone_num=phone, nickname=nickname, role=role_value
                )
        except IntegrityError:
            prof = Profile.objects.get(phone_num=phone)
            if prof.role != role_value:
                return Response(
                    {"detail": "이미 다른 유형으로 가입된 번호입니다.", "registered_role": prof.role},
                    status=status.HTTP_409_CONFLICT,
                )
        return Response(
            {"status": "CREATED", "role": prof.role, "profile_id": prof.id, "redirect_url": redirect_url},
            status=status.HTTP_201_CREATED,
        )

@api_view(["POST"])
def login_youth(request):
    return _login(request, Profile.Role.YOUTH, "/youth/home")

@api_view(["POST"])
def login_nopo(request):
    return _login(request, Profile.Role.MERCHANT, "/nopo/home")