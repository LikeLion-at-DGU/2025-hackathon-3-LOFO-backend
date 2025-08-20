from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Prefetch
from django.db.models import Count, Exists, OuterRef
from outcomes.models import Outcome, OutcomeFile
from .models import Like
from .serializers import OutcomeCardSerializer

from django.db.models import Count, Exists, OuterRef

# @api_view(["GET"])
# def comunity(request): # outcome list
#      category = request.GET.get("category")

#      qs = (
#           Outcome.objects
#           .select_related("mission__request") #제목/카테고리/가게명 접근용
#           .prefetch_related(
#                Prefetch("images", queryset=OutcomeImage.objects.order_by("id"))
#           )
#           .only(
#                "id", "nopo_pick", "created_at",
#                "mission__id", "mission__request__id",
#                "mission__request__title",
#                "mission__request__store_name",
#                "mission__request__category",
#           )
#           .order_by("-created_at")
#      )

#      if category:
#           qs = qs.filter(mission__request__category=category)

#      qs = qs.annotate(like_count=Count("likes", distinct=True))

#      if request.user.is_authenticated and hasattr(request.user, "profile"):
#           qs = qs.annotate(
#                is_liked=Exists(
#                     Like.objects.filter(outcome=OuterRef("pk"), user=request.user.profile)
#                )
#           )
#      else:
#           qs = qs.annotate(is_liked=Exists(Like.objects.none()))
#      for o in qs:
#           o._prefetched_images = list(o.images.all()[:1])

#      ser = OutcomeCardSerializer(qs, many=True, context={"request": request})
#      return Response(ser.data, status=status.HTTP_200_OK)


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