from rest_framework import serializers
from inquiries.models import Request, AiRequest

class RequestListSerializer(serializers.ModelSerializer):
     category_display = serializers.CharField(source="get_category_display", read_only=True)
     status_display = serializers.CharField(source="get_status_display", read_only=True)

     class Meta:
          model = Request
          fields = [
               "id", "store_name", "image", "url",
               "category", "category_display",
               "status", "status_display",
               "title", "content",
               "saved_count",
               "created_at", "updated_at",
          ]


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
