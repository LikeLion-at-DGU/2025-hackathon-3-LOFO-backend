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

    # 1) 같은 (phone, role) 조합이 이미 있으면 바로 로그인 OK
    prof = Profile.objects.filter(phone_num=phone, role=role_value).first()
    if prof:
        return Response(
            {"status": "OK", "role": prof.role, "profile_id": prof.id, "nickname": prof.nickname, "is_authorized": prof.is_authorized, "redirect_url": redirect_url},
            status=status.HTTP_200_OK,
        )

    # 2) 해당 조합이 없으면 -> 가입
    if not nickname:
        return Response(
            {"status": "NEED_SIGNUP", "next": "NEED_NICKNAME"},
            status=status.HTTP_202_ACCEPTED,
        )

    # 닉네임 전역 중복 체크
    if Profile.objects.filter(nickname=nickname).exists():
        return Response(
            {"detail": "이미 사용 중인 닉네임입니다.", "field": "nickname", "code": "nickname_taken"},
            status=status.HTTP_409_CONFLICT,
        )

    # 생성 (경합 대비 트랜잭션 + 무결성 처리)
    try:
        with transaction.atomic():
            prof = Profile.objects.create(
                phone_num=phone, nickname=nickname, role=role_value
            )
    except IntegrityError:
        # 경합으로 닉네임/조합 유니크 충돌 시 재확인
        if Profile.objects.filter(nickname=nickname).exists():
            return Response(
                {"detail": "이미 사용 중인 닉네임입니다.", "field": "nickname", "code": "nickname_taken"},
                status=status.HTTP_409_CONFLICT,
            )
        # (phone, role) 조합이 이미 생겼다면 로그인으로 처리
        prof = Profile.objects.get(phone_num=phone, role=role_value)

    return Response(
        {"status": "CREATED", "role": prof.role, "profile_id": prof.id, "nickname": prof.nickname, "is_authorized": prof.is_authorized, "redirect_url": redirect_url},
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST"])
def login_youth(request):
    return _login(request, Profile.Role.YOUTH, "/youth/home")

@api_view(["POST"])
def login_nopo(request):
    return _login(request, Profile.Role.MERCHANT, "/nopo/home")