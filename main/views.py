from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from django.db.models import Prefetch, Count, Exists, OuterRef, Case, When, BooleanField
from outcomes.models import Outcome, OutcomeFile
from .models import Like
from .serializers import OutcomeCardSerializer

# 발견탭 (커뮤니티)
@api_view(["GET"])
def comunity(request):  # outcome list
    category = request.GET.get("category")

    cover_qs = OutcomeFile.objects.order_by("order", "id")

    qs = (
        Outcome.objects
        .select_related("mission__request") #제목/카테고리/가게명 접근용
        .prefetch_related(
            Prefetch("files", queryset=cover_qs)
        )
        .only(
            "id", "nopo_pick", "created_at",
            "mission__id", "mission__request__id",
            "mission__request__title",
            "mission__request__store_name",
            "mission__request__category",
        )
        .order_by("-created_at")
    )

    if category:
        qs = qs.filter(mission__request__category=category)

    # 좋아요 개수
    qs = qs.annotate(like_count=Count("likes", distinct=True))

    # 좋아요 10개 이상이면 노포픽(배지). 조회 시점에 계산.
    qs = qs.annotate(
        nopo_pick_calc=Case(
            When(like_count__gte=10, then=True), 
            default=False,
            output_field=BooleanField(),
        )
    )

    # 내가 좋아요 눌렀는지
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        qs = qs.annotate(
            is_liked=Exists(
                Like.objects.filter(outcome=OuterRef("pk"), user=request.user.profile)
            )
        )
    else:
        qs = qs.annotate(is_liked=Exists(Like.objects.none()))

    for o in qs:
        # files는 위에서 이미지로만 프리패치됨 → 여기서 슬라이싱해도 추가 쿼리 발생 X
        o._prefetched_cover_files = list(o.files.all()[:1])

    ser = OutcomeCardSerializer(qs, many=True, context={"request": request})
    return Response(ser.data, status=status.HTTP_200_OK)

# 좋아요
@api_view(["POST"])
def like_toggle(request, id: int):
    try:
        outcome = Outcome.objects.get(pk=id)
    except Outcome.DoesNotExist:
        return Response({"detail": "존재하지 않는 결과물입니다."}, status=status.HTTP_404_NOT_FOUND)

    profile = getattr(request.user, "profile", None)
    if not profile:
        return Response({"detail": "프로필이 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

    like, created = Like.objects.get_or_create(user=profile, outcome=outcome)
    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    like_count = Like.objects.filter(outcome=outcome).count()
    return Response({"liked": liked, "like_count": like_count}, status=status.HTTP_200_OK)
