# marketdata/serializers_kyc.py
from rest_framework import serializers
from .models_kyc import KYCSubmission
import hashlib

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class KYCSubmitSerializer(serializers.ModelSerializer):
    aadhaar_number = serializers.CharField(write_only=True, min_length=12, max_length=12)
    class Meta:
        model = KYCSubmission
        fields = ("aadhaar_number", "doc_front", "doc_back")

    def validate(self, data):
        # basic content-type guard
        for k in ("doc_front", "doc_back"):
            f = data[k]
            if f.content_type not in ("image/jpeg", "image/png", "image/heic", "image/heif"):
                raise serializers.ValidationError({k: "Unsupported file type"})
            if f.size > 5 * 1024 * 1024:
                raise serializers.ValidationError({k: "File too large (max 5MB)"})
        return data

    def create(self, validated):
        user = self.context["request"].user
        full = validated.pop("aadhaar_number")
        sub = KYCSubmission.objects.update_or_create(
            user=user,
            defaults=dict(
                aadhaar_last4=full[-4:],
                aadhaar_hash=hashlib.sha256(full.encode()).hexdigest(),
                status=KYCSubmission.Status.PENDING,
                **validated,
            ),
        )[0]
        return sub

class KYCStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = KYCSubmission
        fields = ("status", "submitted_at", "reviewed_at", "aadhaar_last4")
