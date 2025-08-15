from rest_framework import serializers
from .models import Request

class RequestCreateSerializer(serializers.ModelSerializer):
    # 필수로 입력해야 하는 항목
    store_name = serializers.CharField(required=True, allow_blank=False, max_length=50)
    image = serializers.ImageField(required=True, allow_null=False)
    url = serializers.URLField(required=True, allow_blank=False)
    category = serializers.ChoiceField(required=True, choices=Request.Category.choices)
    title = serializers.CharField(required=True, allow_blank=False, max_length=16)
    content = serializers.CharField(required=True, allow_blank=False, style={"base_template": "textarea.html"})

    class Meta:
        model = Request
        fields = ["store_name", "image", "url", "category", "title", "content"]

    def validate_image(self, value):
        # 다중 업로드 시도 차단
        if isinstance(value, (list, tuple)):
            raise serializers.ValidationError("이미지는 한 장만 업로드할 수 있어요.")
        return value

    def validate_title(self, value: str):
        if len(value) > 16:
            raise serializers.ValidationError("제목은 16자 이내로 작성해주세요.")
        return value