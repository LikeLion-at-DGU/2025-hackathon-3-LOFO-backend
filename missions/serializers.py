from rest_framework import serializers
from inquiries.models import Request

class RequestListSerializer(serializers.ModelSerializer):
     owner_name = serializers.CharField(source="owner.user.username", read_only=True)
     category_display = serializers.CharField(source="get_category_display", read_only=True)
     status_display = serializers.CharField(source="get_status_display", read_only=True)
     is_saved = serializers.SerializerMethodField()

     class Meta:
          model = Request
          fields = [
               "id",
               "owner_name",
               "image",
               "url",
               "status",
               "status_display",
               "category",
               "category_display",
               "saved_count",
               "requirement",
               "created_at",
               "is_saved",
          ]

     def get_is_saved(self, obj):
          user = self.context.get("request").user
          if user.is_authenticated:
               return obj.saved_set.filter(user=user).exists()
          return False