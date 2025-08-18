from rest_framework import serializers
from .models import *

class OutcomeCardSerializer(serializers.ModelSerializer):
     cover_image_url = serializers.SerializerMethodField()
     title = serializers.SerializerMethodField()
     store_name = serializers.SerializerMethodField()
     category = serializers.SerializerMethodField()
     category_display = serializers.SerializerMethodField()

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
               "created_at",
          ]

     def get_cover_image_url(self, obj: Outcome):
          # 첫 번째 OutcomeImage 대표 이미지로 사용
          img = next(iter(getattr(obj, "_prefetched_images", []) or obj.images.all()), None)
          if not img or not img.image:
               return None
          request = self.context.get("request")
          url = img.image.url
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
