from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.utils import timezone
from django.db.models import Prefetch, Q

from rest_framework.decorators import api_view, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework import status

from .serializers import RequestCreateSerializer, RequestUpdateSerializer, NopoFeedbackSerializer
from outcomes.models import Outcome, OutcomeFile
from main.serializers import OutcomeCardSerializer
from accounts.models import Profile
from .models import Request, NopoFeedback, Saved
from missions.models import Mission, MissionStep

import io
import os
import zipfile


# 상인 홈: 요청작성 링크 + 진행현황 집계 + 최근 요청글 3개 요청
@api_view(["GET"])
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
            "category": obj.category,                    # ex) "POSTER_FLYER"
            "category_label": obj.get_category_display(),# ex) "포스터·전단"
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


# 요청탭
@api_view(["GET"])
def nopo_request(request):
    profile = request.user.profile  # 로그인 전제

    # 1) 기본정보 + 썸네일 + 상태 필터 / 최신순 정렬
    status_q = (request.GET.get("status") or "").upper()
    qs = Request.objects.filter(owner=profile)
    if status_q in (Request.Status.OPEN, Request.Status.ONGOING, Request.Status.CLOSED):
        qs = qs.filter(status=status_q)
    qs = qs.only("id", "store_name", "title", "image", "status").order_by("-created_at")

    today = timezone.now().date()
    items = []

    for obj in qs:
        # 공통
        url_attr = getattr(getattr(obj, "image", None), "url", None)
        image_url = request.build_absolute_uri(url_attr) if url_attr else ""

        item = {
            "id": obj.id,
            "store_name": obj.store_name,
            "title": obj.title,
            "image_url": image_url,
            "status": obj.status,  
        }

        # 상태별 추가
        if obj.status == Request.Status.OPEN:
            item["links"] = {
                "edit": reverse("nopo-request-edit", kwargs={"request_id": obj.id}),
                "end":  reverse("nopo-request-end",  kwargs={"request_id": obj.id}),
            }

        elif obj.status == Request.Status.ONGOING:
            # 해당 요청의 진행중 미션 1개 기준(일반 전제)
            mission = (
                Mission.objects
                .filter(request=obj, status=Mission.Status.IN_PROGRESS)
                .prefetch_related("steps")
                .order_by("-created_at")
                .first()
            )

            step_no = None
            deadline_iso = None
            dday = None

            if mission:
                if mission.deadline:
                    deadline_date = mission.deadline.date()
                    deadline_iso = mission.deadline.isoformat()
                    dday = (deadline_date - today).days

                # TODO_or_DOING 중 가장 낮은 step_no, 없으면 마지막 step_no
                steps = sorted(mission.steps.all(), key=lambda s: s.step_no)
                current = next(
                    (s for s in steps if s.status in (MissionStep.StepStatus.TODO, MissionStep.StepStatus.DOING)),
                    None
                )
                step_no = current.step_no if current else (steps[-1].step_no if steps else None)

            item["progress"] = {
                "step_no": step_no,
                "deadline": deadline_iso,
                "dday": dday,
            }

        items.append(item)

    return Response(
        {
            "links": {"request_create": reverse("nopo-request-create")},  # /nopo/request/create
            "items": items,
        },
        status=status.HTTP_200_OK,
    )


# 요청입력
@api_view(["POST"])
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


# 요청수정
@api_view(["PATCH"])
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


# 요청종료
@api_view(["POST"])
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


# 상인 마이페이지
@api_view(["GET"])
def nopo_received(request):
    profile = request.user.profile  

    # 진행중 요청 개수
    ongoing_count = Request.objects.filter(
        status=Request.Status.ONGOING,
        owner=profile
    ).count()

    # 커버 후보
    cover_qs = (
        OutcomeFile.objects
        .filter(
            Q(kind=OutcomeFile.Kind.IMAGE) |
            Q(mime_type__startswith="text/") |
            Q(file__iendswith=".txt")
        )
        .order_by("order", "id")
    )

    # Outcome 목록 (상인 요청에 제출된 것들)
    outcomes_qs = (
        Outcome.objects
        .select_related("mission__request")
        .prefetch_related(Prefetch("files", queryset=cover_qs))
        .filter(mission__request__owner=profile)
        .order_by("-created_at")
    )

    # Serializer가 사용할 1개 후보만 심어주기: 이미지 우선 → 없으면 TXT
    for o in outcomes_qs:
        files = list(o.files.all())
        img = next((f for f in files if f.kind == OutcomeFile.Kind.IMAGE), None)
        txt = None
        if not img:
            txt = next((
                f for f in files
                if (getattr(f, "mime_type", "") or "").startswith("text/") or
                (getattr(getattr(f, "file", None), "name", "") or "").lower().endswith(".txt")
            ), None)
        o._prefetched_cover_files = [img or txt] if (img or txt) else []
    # 직렬화
    data = {
        "ongoing_count": ongoing_count,
        "outcomes": OutcomeCardSerializer(outcomes_qs, many=True, context={"request": request}).data,
    }
    return Response(data, status=status.HTTP_200_OK)


# 후기작성 (피드백) 폼 리소스
@api_view(["GET"])
def nopo_feedback_form_data(request, outcome_id: int):
    profile = request.user.profile

    # 권한 확인: 이 상인이 소유한 요청의 outcome만 접근 가능
    outcome = (
        Outcome.objects
        .select_related("mission__request")
        .filter(pk=outcome_id, mission__request__owner=profile)
        .first()
    )
    if not outcome:
        return Response({"detail": "접근 권한이 없거나 존재하지 않는 결과물입니다."}, status=status.HTTP_404_NOT_FOUND)

    # 이미 제출했는지(한 번만 가능)
    if NopoFeedback.objects.filter(outcome_id=outcome_id, author=profile).exists():
        return Response({"detail": "이미 피드백을 제출했습니다."}, status=status.HTTP_409_CONFLICT)

    # 1) 이미지 수집 (있으면 이미지만 반환)
    images = (
        OutcomeFile.objects
        .filter(outcome=outcome, kind=getattr(OutcomeFile.Kind, "IMAGE", None))
        .order_by("order", "id")
    )
    image_urls = [
        request.build_absolute_uri(f.file.url)
        for f in images
        if getattr(getattr(f, "file", None), "url", None)
    ]
    if image_urls:
        return Response({
            "outcome_id": outcome.id,
            "images": image_urls,  # 1개거나 N개
            "texts": []            # 이미지가 있으면 텍스트는 비움
        }, status=status.HTTP_200_OK)

    # 2) TXT 수집 (utf-8 → cp949 → latin-1 순서 시도, 실패 시 치환)
    def _read_text_all(file_field) -> str:
        file_field.open("rb")
        try:
            raw = file_field.read()
            for enc in ("utf-8", "cp949", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="replace")  # 최종 fallback
        finally:
            file_field.close()

    # Kind.TXT가 없더라도 MIME/확장자로 텍스트 판별
    non_images = (
        OutcomeFile.objects
        .filter(outcome=outcome)
        .exclude(kind=getattr(OutcomeFile.Kind, "IMAGE", None))
        .order_by("order", "id")
    )
    texts = []
    for f in non_images:
        mime = (getattr(f, "mime_type", "") or "").lower()
        name = (getattr(getattr(f, "file", None), "name", "") or "").lower()
        if mime.startswith("text/") or name.endswith(".txt"):
            try:
                texts.append(_read_text_all(f.file))
            except Exception:
                texts.append("")

    if texts:
        return Response({
            "outcome_id": outcome.id,
            "images": [],    # 텍스트가 있으면 이미지는 비움
            "texts": texts   # 한 개여도 리스트로
        }, status=status.HTTP_200_OK)

    # 3) 아무 파일도 없으면
    return Response({"detail": "표시할 파일이 없습니다."}, status=status.HTTP_404_NOT_FOUND)


# 후기작성 (피드백)
@api_view(["POST"])
def nopo_received_feedback(request):

    author = request.user.profile          
    outcome_id = request.data.get("outcome_id")
    if not outcome_id:
        return Response({"detail": "outcome_id가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

    # 이미 제출했는지(한 번만 가능)
    if NopoFeedback.objects.filter(outcome_id=outcome_id, author=author).exists():
        return Response({"detail": "이미 피드백을 제출했습니다."}, status=status.HTTP_409_CONFLICT)

    payload = {
        "outcome": outcome_id,
        "overall_satisfaction": request.data.get("overall_satisfaction"),
        "reflection_level": request.data.get("reflection_level"),
        "practical_use": request.data.get("practical_use"),
        "comment": request.data.get("comment"),
    }

    ser = NopoFeedbackSerializer(data=payload)
    ser.is_valid(raise_exception=True)
    obj = ser.save(author=author)  # 생성만

    return Response(NopoFeedbackSerializer(obj).data, status=status.HTTP_201_CREATED)


# 청년의 결과물 (outcome) 다운로드 
@api_view(["GET"])
def nopo_received_download(request, outcome_id: int):
    outcome = Outcome.objects.get(pk=outcome_id)  # 존재 전제

    # 이미지 수집
    images = list(
        OutcomeFile.objects.filter(
            outcome=outcome, kind=OutcomeFile.Kind.IMAGE
        ).order_by("order", "id")
    )

    # 텍스트 수집 (Kind.TXT 또는 text/* 혹은 .txt)
    text_qs = OutcomeFile.objects.filter(outcome=outcome).exclude(kind=OutcomeFile.Kind.IMAGE).order_by("order", "id")
    texts = [f for f in text_qs if f.kind == OutcomeFile.Kind.TXT
            or (getattr(f, "mime_type", "") or "").startswith("text/")
            or f.file.name.lower().endswith(".txt")]

    total_cnt = len(images) + len(texts)
    if total_cnt == 0:
        return Response({"detail": "다운로드할 파일이 없습니다."}, status=status.HTTP_404_NOT_FOUND)

    # 단일 파일이면 바로 내려주기
    if total_cnt == 1:
        if images:
            f = images[0]
            fp = open(f.file.path, "rb")
            resp = FileResponse(fp)
            resp["Content-Disposition"] = f'attachment; filename="{os.path.basename(f.file.name)}"'
            return resp
        else:
            f = texts[0]
            fp = open(f.file.path, "rb")
            resp = FileResponse(fp, content_type="text/plain")
            # 확장자 보정
            name = os.path.basename(f.file.name)
            if not name.lower().endswith(".txt"):
                name = os.path.splitext(name)[0] + ".txt"
            resp["Content-Disposition"] = f'attachment; filename="{name}"'
            return resp

    # 2개 이상이면 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 이미지: 원본 파일명
        for f in images:
            zf.write(f.file.path, arcname=os.path.basename(f.file.name))
        # 텍스트: .txt로 강제
        for idx, f in enumerate(texts, start=1):
            try:
                # 원본을 읽어 디코딩/리인코딩까지 할 필요는 없음 — 바이너리 그대로
                zf.write(f.file.path, arcname=f"text_{idx}.txt")
            except Exception:
                # 파일 접근 실패 시 빈 파일 넣기
                zf.writestr(f"text_{idx}.txt", "")

    buf.seek(0)
    resp = FileResponse(buf, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="outcome_{outcome.id}_files.zip"'
    return resp

# 찜하기 토글
@api_view(["POST"])
def saved_toggle(request, id: int):
    try:
        req = Request.objects.get(pk=id)
    except Request.DoesNotExist:
        return Response({"detail": "존재하지 않는 요청글입니다."}, status=status.HTTP_404_NOT_FOUND)

    profile = getattr(request.user, "profile", None)
    if not profile:
        return Response({"detail": "프로필이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

    saved, created = Saved.objects.get_or_create(user=profile, request=req)
    if not created:
        saved.delete()
        is_saved = False
    else:
        is_saved = True

    saved_count = Saved.objects.filter(request=req).count()

    return Response({"saved": is_saved, "saved_count": saved_count}, status=status.HTTP_200_OK)
