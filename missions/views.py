from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
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

import os, base64, mimetypes
import fitz  # PyMuPDF
from .services.openai_service import *
from outcomes.models import *


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
     
     if Mission.objects.filter(youth=youth, status=Mission.Status.IN_PROGRESS).exists():
          return Response(
               {"detail": "이미 진행 중인 미션이 있습니다. 완료/포기/만료 후 새 계획을 만들 수 있어요."},
               status=status.HTTP_409_CONFLICT
          )

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

          # Request 상태를 ONGOING 으로 업데이트
          req_obj.status = Request.Status.IN_PROGRESS
          req_obj.save(update_fields=["status"])

          mission = Mission.objects.create(
               request=req_obj,
               youth=youth,
               deadline=deadline_dt,
               status=Mission.Status.IN_PROGRESS,
               ai_model="gpt-3.5-turbo",
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

ALLOWED_FEEDBACK_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".mp4"}  # 중간 피드백 허용
MAX_FILE_MB = 6

def _ext_of(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()

def _validate_uploads(files):
    bad_ext, too_big = [], []
    for f in files:
        ext = _ext_of(f.name)
        size_mb = getattr(f, "size", 0) / (1024 * 1024)
        if ext not in ALLOWED_FEEDBACK_EXTS:
            bad_ext.append(f.name)
        if size_mb > MAX_FILE_MB:
            too_big.append(f.name)
    return bad_ext, too_big

def _img_to_data_url(uploaded_file) -> str | None:
    name = (uploaded_file.name or "").lower()
    ct   = getattr(uploaded_file, "content_type", "") or mimetypes.guess_type(name)[0] or ""
    if not (name.endswith((".png", ".jpg", ".jpeg")) or (ct and ct.startswith("image/"))):
        return None
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    b64 = base64.b64encode(raw).decode("utf-8")
    mime = ct or ("image/png" if name.endswith(".png") else "image/jpeg")
    return f"data:{mime};base64,{b64}"

def _pdf_to_text(uploaded_file, max_pages=5, max_chars=4000) -> str | None:
    name = (uploaded_file.name or "").lower()
    if not name.endswith(".pdf"):
        return None
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    text = ""
    try:
        with fitz.open(stream=raw, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                text += page.get_text("text") or ""
                if len(text) >= max_chars:
                    text = text[:max_chars] + "…"
                    break
    except Exception:
        return None
    return text.strip() or None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def mission(request):
    """
    POST /youth/mission
    form-data:
      - mission_id: int (필수)
      - step_no: 1|2 (필수)
      - note: string (선택)
      - files: [file...] (선택, 여러 개 가능)
    동작:
      - 확장자/용량 검증 (허용: png/jpg/jpeg/pdf/mp4, 6MB 이하)
      - 2단계 피드백은 1단계가 DONE이어야 허용(순서 강제)
      - 파일은 저장하지 않음 (이미지/텍스트만 분석)
      - AI 피드백 생성 후 반환, feedback_count +1
    """
    mission_id = request.data.get("mission_id")
    step_no_raw = request.data.get("step_no")
    note = request.data.get("note", "")

    if not mission_id or not step_no_raw:
        return Response({"detail": "mission_id와 step_no가 필요합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        step_no = int(step_no_raw)
    except ValueError:
        return Response({"detail": "step_no는 정수여야 합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    if step_no not in (1, 2):
        return Response({"detail": "step_no는 1 또는 2만 가능합니다."},
                        status=status.HTTP_400_BAD_REQUEST)

    mission = get_object_or_404(Mission, pk=mission_id)
    step = get_object_or_404(MissionStep, mission=mission, step_no=step_no)

    # --- 순서 강제: 2단계는 1단계가 DONE이어야 함 ---
    if step_no == 2:
        try:
            s1 = MissionStep.objects.get(mission=mission, step_no=1)
            if s1.status != MissionStep.StepStatus.DONE:
                return Response({"detail": "2단계 피드백은 1단계를 먼저 완료해 주세요."},
                                status=status.HTTP_409_CONFLICT)
        except MissionStep.DoesNotExist:
            return Response({"detail": "1단계 정보가 없습니다."},
                            status=status.HTTP_400_BAD_REQUEST)

    files = request.FILES.getlist("files")

    # --- 확장자/용량 검증 ---
    bad_ext, too_big = _validate_uploads(files)
    if too_big:
        return Response({"detail": f"파일 용량 초과(>{MAX_FILE_MB}MB): {', '.join(too_big)}"},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if bad_ext:
        return Response({"detail": f"허용되지 않는 확장자: {', '.join(bad_ext)}"},
                        status=status.HTTP_400_BAD_REQUEST)

    # --- 멀티모달 입력 구성 ---
    image_data_urls, pdf_texts, file_names = [], [], []
    for f in files:
        file_names.append(f.name)
        # 이미지 → base64 data URL
        url = _img_to_data_url(f)
        if url:
            image_data_urls.append(url)
            continue
        # PDF → 텍스트 추출
        t = _pdf_to_text(f)
        if t:
            pdf_texts.append(t)
        # mp4 등은 이름만 전달(내용 분석 X)

    # 목표 문장 구성(요청 제목/내용 활용)
    req = mission.request
    goal_text = (getattr(req, "title", None) or getattr(req, "name", None) or "").strip()
    desc_text = (getattr(req, "content", None) or getattr(req, "description", None) or "").strip()
    goal = goal_text or desc_text or "요청 목표"

    # --- AI 피드백 생성 ---
    try:
        feedback = build_step_feedback(
            goal=goal,
            step_no=step_no,
            step_title=step.title or f"{step_no}단계",
            note=note,
            image_data_urls=image_data_urls,
            file_names=file_names,
            extra_texts=pdf_texts,
        )
    except Exception as e:
        return Response({"detail": f"AI 피드백 생성 실패: {e}"},
                        status=status.HTTP_502_BAD_GATEWAY)

    # --- 요청 횟수 증가 ---
    step.feedback_count = (step.feedback_count or 0) + 1
    step.save(update_fields=["feedback_count", "updated_at"])

    return Response({
        "mission_id": mission.id,
        "step_no": step_no,
        "feedback": feedback,
        "feedback_count": step.feedback_count,
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
def mission_done(request):
     mission_id = request.data.get("mission_id")
     step_no = request.data.get("step_no")

     if not mission_id or not step_no:
          return Response({"detail": "mission_id와 step_no가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

     mission = get_object_or_404(Mission, pk=mission_id)

     # 순서 강제: 2단계 완료는 1단계가 DONE일 때만
     if step_no == 2:
          s1 = get_object_or_404(MissionStep, mission=mission, step_no=1)
          if s1.status != MissionStep.StepStatus.DONE:
               return Response({"detail": "2단계를 완료하려면 1단계를 먼저 완료해 주세요."}, status=status.HTTP_409_CONFLICT)

     step = get_object_or_404(MissionStep, mission=mission, step_no=step_no)

     # 완료 처리
     step.mark_done()

     return Response({
          "detail": f"{step_no}단계 미션 완료.",
          "mission_id": mission.id,
          "step_no": step_no,
          "status": step.status,
          "completed_at": step.completed_at,
          "all_steps": list(mission.steps.order_by("step_no").values("step_no", "status", "completed_at")),
     }, status=status.HTTP_200_OK)


# 파일 kind 추정을 위한 간단 유틸 (OutcomeFile.Kind 값과 맞춤)
def _guess_kind_by_ext(name: str) -> str:
     n = (name or "").lower()
     if n.endswith((".png", ".jpg", ".jpeg")):
          return "IMAGE"
     if n.endswith(".pdf"):
          return "PDF"
     if n.endswith(".mp4"):
          return "VIDEO"
     return "IMAGE"  # 기본값


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def mission_submit(request):
     mission_id = request.data.get("mission_id")
     if not mission_id:
          return Response({"detail": "mission_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

     mission = get_object_or_404(Mission, pk=mission_id)

     # 업로드 파일 필수
     files = request.FILES.getlist("files")
     if not files:
          return Response({"detail": "최종 제출에는 files가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

     # 확장자/용량 검증
     bad_ext, too_big = _validate_uploads(files)
     if too_big:
          return Response({"detail": f"파일 용량 초과(>{MAX_FILE_MB}MB): {', '.join(too_big)}"},
                         status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
     if bad_ext:
          return Response({"detail": f"허용되지 않는 확장자: {', '.join(bad_ext)}"},
                         status=status.HTTP_400_BAD_REQUEST)

     # 3단계 객체
     s3 = get_object_or_404(MissionStep, mission=mission, step_no=3)

     # Outcome.owner 
     owner_profile = getattr(mission.request, "owner", None) or request.user.profile

     with transaction.atomic():
          # 1. Outcome 생성 (결과물 묶음)
          outcome = Outcome.objects.create(
               mission=mission,
               youth=request.user.profile,# 제출자(청년)
               owner=owner_profile, # 요청 주인(상인)
               nopo_pick=False,
          )

          # 2.OutcomeFile 생성 (업로드 파일 각각 저장)
          file_objs = []
          for idx, f in enumerate(files):
               file_objs.append(OutcomeFile(
                    outcome=outcome,
                    kind=_guess_kind_by_ext(f.name), # IMAGE / PDF / VIDEO
                    file=f, # 실제 파일
                    mime_type=getattr(f, "content_type", "") or "",
                    size_bytes=getattr(f, "size", None),
                    order=idx, # 정렬 순서
               ))
          OutcomeFile.objects.bulk_create(file_objs)
     
          # 3. 3단계 완료처리
          s3.mark_done()

          # 4. 미션 전체 완료
          mission.status = Mission.Status.DONE
          mission.save(update_fields=["status", "updated_at"])

          # 5. Request 상태도 'CLOSED'로 변경
          try:
               req = mission.request
               req.status = Request.Status.CLOSED
               req.save(update_fields=["status", "updated_at"])
          except Exception as e:
               raise RuntimeError(f"Request 상태 업데이트 실패: {str(e)}")

     # 6. 최종 응답
     return Response({
          "detail": "최종 결과물을 제출했어요.",
          "outcome_id": outcome.id,
          "files": [
               {"id": f.id, "kind": f.kind, "name": f.file.name, "size": f.size_bytes}
               for f in outcome.files.all()
          ],
          "mission_status": mission.status,  # "DONE"
          "steps": list(mission.steps.order_by("step_no").values("step_no", "status", "completed_at")),
          "request_status": getattr(mission.request, "status", None),  # "CLOSED" 기대
     }, status=status.HTTP_201_CREATED)