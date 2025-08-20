from .services.openai_service import build_plan

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404

from datetime import datetime, time

from inquiries.models import Request, AiRequest, Saved
from accounts.models import Profile
from .models import Mission, MissionStep
from .serializers import RequestListSerializer, AiRequestListSerializer


# 청년 홈: 상인 요청 리스트
@api_view(["GET"])
def home(request):
    category = request.GET.get("category")
    sort = request.GET.get("sort", "latest")  # 정렬 기준 기본 - 최신순

    qs = Request.objects.filter(status="OPEN")  # status = OPEN 인 것만
    if category:
        qs = qs.filter(category=category)

    if sort == "popular":  # 찜 많은 순
        qs = qs.order_by("-saved_count")
    else:
        qs = qs.order_by("-created_at")

    serializer = RequestListSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# 청년 홈2: AI 요청 리스트
@api_view(["GET"])
def home_ai(request):
    category = request.GET.get("category")
    sort = request.GET.get("sort", "latest")

    qs = AiRequest.objects.filter(status="IN_PROGRESS")
    if category:
        qs = qs.filter(category=category)

    if sort == "popular":
        qs = qs.order_by("-saved_count")
    else:  # 최신순
        qs = qs.order_by("-created_at")

    serializer = AiRequestListSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def mission_detail(request, id):
    req = get_object_or_404(Request, pk=id)
    serializer = RequestListSerializer(req)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_mission(request):
    req_id = request.data.get("request_id")
    if not req_id:
        return Response({"detail": "request_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

    req = get_object_or_404(Request, pk=req_id)

    # 로그인 사용자 프로필
    try:
        profile: Profile = request.user.profile
    except Exception:
        return Response({"detail": "프로필이 필요합니다."}, status=status.HTTP_403_FORBIDDEN)

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


def _parse_deadline_to_dt(deadline_str: str):
    """
    'YYYY-MM-DD' 기본. 'YYYY.MM.DD'나 'YYYY/MM/DD'도 허용.
    Date만 들어오면 23:59:59 로 마감 처리.
    """
    if not deadline_str:
        return None
    s = deadline_str.replace(".", "-").replace("/", "-")
    d = parse_date(s)
    if not d:
        return None
    dt = datetime.combine(d, time(23, 59, 59))
    return timezone.make_aware(dt)


@api_view(["POST"])
@permission_classes([IsAuthenticated])  # 인증이 필요 없다면 제거
def generate_plan(request):
    """
    POST /youth/plan
    body: { "request_id": number, "goal": string, "deadline": "YYYY-MM-DD" }
    성공 시: 미션 & 스텝 생성 + 생성된 데이터 반환
    """
    req_id = request.data.get("request_id")
    goal = request.data.get("goal")
    deadline_str = request.data.get("deadline")

    if not req_id or not goal or not deadline_str:
        return Response({"detail": "request_id, goal, deadline 필수"}, status=status.HTTP_400_BAD_REQUEST)

    # 요청 존재 확인
    try:
        req_obj = Request.objects.get(pk=req_id)
    except Request.DoesNotExist:
        return Response({"detail": "존재하지 않는 요청입니다."}, status=status.HTTP_404_NOT_FOUND)

    # 로그인 사용자 프로필
    try:
        youth: Profile = request.user.profile
    except Exception:
        return Response({"detail": "프로필이 필요합니다."}, status=status.HTTP_403_FORBIDDEN)

    # 마감일 파싱 (USE_TZ 설정에 맞게 aware/naive 반환되는 헬퍼 사용)
    deadline_dt = _parse_deadline_to_dt(deadline_str)
    if not deadline_dt:
        return Response({"detail": "deadline 형식이 올바르지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)

    # Request의 제목/내용을 안전하게 가져와서 AI에 전달
    req_title = getattr(req_obj, "title", None) or getattr(req_obj, "name", None) or ""
    req_desc  = getattr(req_obj, "content", None) or getattr(req_obj, "description", None) or ""

    # AI로 플랜 생성 (JSON steps 3개)
    try:
        safe_deadline_str = str(deadline_str).replace(".", "-").replace("/", "-")
        plan_json = build_plan(
            goal=goal,
            deadline_date_str=safe_deadline_str,
            request_title=req_title,
            request_desc=req_desc,
        )
    except Exception as e:
        return Response({"detail": f"AI 계획 생성 실패: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

    steps = plan_json.get("steps", [])
    if not isinstance(steps, list) or len(steps) != 3:
        return Response({"detail": "AI가 3단계 계획을 반환하지 않았습니다."}, status=status.HTTP_502_BAD_GATEWAY)

    # DB 저장 (원자적)
    with transaction.atomic():
        # 같은 Request에 여러 Mission 허용: 버전 자동 증가
        next_ver = Mission.objects.filter(request=req_obj).count() + 1

        mission = Mission.objects.create(
            request=req_obj,
            youth=youth,
            deadline=deadline_dt,
            status=Mission.Status.IN_PROGRESS,
            ai_model="gpt-4o-mini",
            ai_plan_ver=next_ver,
            plan=plan_json,  # 원본 JSON 보관
        )

        # 스텝 생성 (1~3 고정) + reference(list[str])를 TextField로 저장 가능한 문자열로 변환
        step_objs = []
        for idx, s in enumerate(steps, start=1):
            due_str = s.get("due")  # "YYYY-MM-DD" or None
            due_date = None
            if due_str:
                s2 = str(due_str).replace(".", "-").replace("/", "-")
                due_date = parse_date(s2)

            ref_val = s.get("reference") or []
            if isinstance(ref_val, list):
                reference_text = "- " + "\n- ".join([str(x).strip() for x in ref_val if str(x).strip()])
            else:
                reference_text = str(ref_val).strip()

            step_objs.append(MissionStep(
                mission=mission,
                step_no=idx,  # 1~3
                title=str(s.get("title", "")).strip()[:200],
                description=str(s.get("description", "")).strip(),
                reference=reference_text,
                due=due_date,
            ))
        MissionStep.objects.bulk_create(step_objs)

    # 응답(필요시 Serializer로 교체 가능)
    return Response({
        "mission": {
            "id": mission.id,
            "request_id": mission.request_id,
            "youth_id": mission.youth_id,
            "deadline": mission.deadline,
            "status": mission.status,
            "ai_model": mission.ai_model,
            "ai_plan_ver": mission.ai_plan_ver,
        },
        "steps": [
            {
                "step_no": s.step_no,
                "title": s.title,
                "description": s.description,
                "reference": s.reference,  # 불릿 텍스트
                "due": s.due,
            } for s in mission.steps.order_by("step_no")
        ],
    }, status=status.HTTP_201_CREATED)
