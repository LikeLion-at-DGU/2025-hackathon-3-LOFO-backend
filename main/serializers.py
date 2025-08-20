from rest_framework import serializers
from django.conf import settings
from outcomes.models import Outcome, OutcomeFile
from django.urls import reverse

class OutcomeCardSerializer(serializers.ModelSerializer):
    cover_image_url = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Outcome
        fields = [
            "id",
            "cover_image_url",
            "title",
            "store_name",
            "category",
            "category_display",
            "nopo_pick",
            "like_count",
            "is_liked",
            "created_at",
        ]

    def get_cover_image_url(self, obj: Outcome):
        """
        대표 썸네일 우선순위
        1) IMAGE → 원본 이미지
        2) VIDEO → /outcomes/files/<id>/video-thumb
        3) PDF   → 고정 아이콘 이미지
        """
        request = self.context.get("request")

        # ① 뷰에서 미리 슬라이스해서 넣어준 경우(권장)
        f = next(iter(getattr(obj, "_prefetched_cover_files", [])), None)

        # ② 없으면 직접 조회 (order, id 오름차순)
        if not f:
            f = obj.files.order_by("order", "id").first()
        if not f:
            return None

        # IMAGE → 그대로
        if f.kind == OutcomeFile.Kind.IMAGE:
            try:
                url = f.file.url
                return request.build_absolute_uri(url) if request else url
            except Exception:
                return None

        # VIDEO → 썸네일 엔드포인트
        if f.kind == OutcomeFile.Kind.VIDEO:
            thumb_url = reverse("outcomes:video-thumb", args=[f.id])
            return request.build_absolute_uri(thumb_url) if request else thumb_url

        # PDF → 고정 아이콘
        if f.kind == OutcomeFile.Kind.PDF:
            static_path = getattr(settings, "OUTCOME_PDF_THUMB_STATIC", "static/images/pdf-thumb.png")
            return request.build_absolute_uri(static_path) if request else static_path

        return None

    def get_title(self, obj: Outcome):
        return getattr(obj.mission.request, "title", "")

    def get_store_name(self, obj: Outcome):
        return getattr(obj.mission.request, "store_name", "")

    def get_category(self, obj: Outcome):
        return getattr(obj.mission.request, "category", None)

    def get_category_display(self, obj: Outcome):
        req = obj.mission.request
        return req.get_category_display() if req else None
