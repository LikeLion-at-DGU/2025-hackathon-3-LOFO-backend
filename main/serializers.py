
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

        # ① 프리패치된 후보 1개가 있으면 그거 사용
        prefetched = list(getattr(obj, "_prefetched_cover_files", [])) or []

        def _is_text(f):
            mt = (getattr(f, "mime_type", "") or "").lower()
            name = (getattr(getattr(f, "file", None), "name", "") or "").lower()
            return mt.startswith("text/") or name.endswith(".txt")

        # 프리패치에서 우선 결정
        if prefetched:
            f = prefetched[0]
            if f.kind == OutcomeFile.Kind.IMAGE and getattr(getattr(f, "file", None), "url", None):
                url = f.file.url
                return request.build_absolute_uri(url) if request else url
            if _is_text(f):
                # TXT → 전체 본문
                f.file.open("rb")
                try:
                    raw = f.file.read()
                    for enc in ("utf-8", "cp949", "latin-1"):
                        try:
                            return raw.decode(enc)
                        except UnicodeDecodeError:
                            continue
                    return raw.decode("utf-8", errors="replace")
                finally:
                    f.file.close()
            return None

        # ② 프리패치 없으면 DB 조회 (이미지 우선 → 텍스트)
        f_img = obj.files.filter(kind=OutcomeFile.Kind.IMAGE).order_by("order", "id").first()
        if f_img and getattr(getattr(f_img, "file", None), "url", None):
            url = f_img.file.url
            return request.build_absolute_uri(url) if request else url

        f_txt = obj.files.filter(
            Q(mime_type__startswith="text/") | Q(file__iendswith=".txt")
        ).order_by("order", "id").first()
        if f_txt and getattr(f_txt, "file", None):
            f_txt.file.open("rb")
            try:
                raw = f_txt.file.read()
                for enc in ("utf-8", "cp949", "latin-1"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="replace")
            finally:
                f_txt.file.close()

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
