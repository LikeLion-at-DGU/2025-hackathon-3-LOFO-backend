from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    phone_num = serializers.CharField()
    nickname = serializers.CharField(required=False, allow_blank=True)  # 빈 문자열이 와도 통과

    def validate_phone_num(self, v):
        digits = ''.join(ch for ch in v if ch.isdigit())  # 010-1234-5678 → 01012345678
        if len(digits) not in (10, 11):
            raise serializers.ValidationError("유효한 전화번호 형식이 아닙니다.")
        return digits