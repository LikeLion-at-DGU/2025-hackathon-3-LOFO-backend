from rest_framework import serializers
from inquiries.models import Request, AiRequest

class RequestListSerializer(serializers.ModelSerializer):
     category_display = serializers.CharField(source="get_category_display", read_only=True)
     status_display = serializers.CharField(source="get_status_display", read_only=True)
     is_saved = serializers.SerializerMethodField(read_only=True)

     class Meta:
          model = Request
          fields = [
               "id", "store_name", "image", "url",
               "category", "category_display",
               "status", "status_display",
               "title", "content",
               "saved_count", "is_saved",
               "created_at", "updated_at",
          ]

     def get_is_saved(self, obj):
          request = self.context.get("request")
          if not request or not request.user.is_authenticated:
               return False
          profile = getattr(request.user, "profile", None)
          if profile is None:
               return False
          return obj.saves.filter(user=profile).exists()


class AiRequestListSerializer(serializers.ModelSerializer):
     category_display = serializers.CharField(source="get_category_display", read_only=True)
     status_display = serializers.CharField(source="get_status_display", read_only=True)

     class Meta:
          model = AiRequest
          fields = [
               "id", "store_name", "image", "url",
               "category", "category_display",
               "status", "status_display",
               "title", "content",
               "saved_count",
               "created_at", "updated_at",
          ]
