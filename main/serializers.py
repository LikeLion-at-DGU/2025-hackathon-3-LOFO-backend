from django.conf import settings
from django.urls import reverse
from rest_framework import serializers
from outcomes.models import Outcome, OutcomeFile
from typing import Optional
import io

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
        request = self.context.get("request")

        # 뷰에서 미리 넣어준 프리패치가 있으면 그 안에서 우선 탐색
        prefetched = list(getattr(obj, "_prefetched_cover_files", [])) or []

        def first_by_kind(files, kind):
            for f in files:
                if getattr(f, "kind", None) == kind:
                    return f
            return None

        # 프리패치에서 우선 탐색
        f_img = first_by_kind(prefetched, OutcomeFile.Kind.IMAGE)
        f_txt = first_by_kind(prefetched, OutcomeFile.Kind.TXT) if not f_img else None

        # DB 조회 (order, id 오름차순)
        if not f_img:
            f_img = (
                obj.files.filter(kind=OutcomeFile.Kind.IMAGE)
                .order_by("order", "id")
                .first()
            )
        if not f_img and not f_txt:
            f_txt = (
                obj.files.filter(kind=OutcomeFile.Kind.TXT)
                .order_by("order", "id")
                .first()
            )

        # 1) IMAGE → 절대 URL
        if f_img and getattr(f_img, "file", None) and getattr(f_img.file, "url", None):
            url = f_img.file.url
            return request.build_absolute_uri(url) if request else url

        # 2) TXT → 전체 본문 반환 (utf-8 → cp949 → latin-1 순서 시도, 실패 시 치환)
        if f_txt and getattr(f_txt, "file", None):
            f_txt.file.open("rb")
            try:
                raw = f_txt.file.read()
                for enc in ("utf-8", "cp949", "latin-1"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="replace")  # 최종 fallback
            finally:
                f_txt.file.close()

        # 3) 없음
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
