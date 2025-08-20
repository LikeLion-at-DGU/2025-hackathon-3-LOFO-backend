from rest_framework import serializers
from outcomes.models import Outcome, OutcomeFile


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
        OutcomeFile 중 kind="IMAGE" 인 첫 번째 파일을 대표 이미지로 사용
        뷰에서 _prefetched_images 를 세팅해두면 추가 쿼리 없이 가져옴
        """
        # 뷰에서 미리 넣어둔 경우 우선 사용
        img = next(iter(getattr(obj, "_prefetched_images", [])), None)

        # 없으면 직접 조회
        if not img:
            img = obj.files.filter(kind="IMAGE").order_by("id").first()

        if not img or not getattr(img, "file", None):
            return None

        try:
            url = img.file.url
        except Exception:
            return None

        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_title(self, obj: Outcome):
        return getattr(obj.mission.request, "title", "")

    def get_store_name(self, obj: Outcome):
        return getattr(obj.mission.request, "store_name", "")

    def get_category(self, obj: Outcome):
        return getattr(obj.mission.request, "category", None)

    def get_category_display(self, obj: Outcome):
        req = obj.mission.request
        return req.get_category_display() if req else None
