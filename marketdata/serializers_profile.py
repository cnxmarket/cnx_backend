# marketdata/serializers_profile.py
from django.contrib.auth import password_validation
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models_profile import UserProfile
from .models_kyc import KYCSubmission  # you already created this

User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UserProfile
        fields = ("avatar_url",)  # write avatar later via multipart if you want

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj and obj.avatar and hasattr(obj.avatar, "url"):
            url = obj.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None


class MeSerializer(serializers.ModelSerializer):
    # Read-only computed fields
    full_name = serializers.SerializerMethodField()
    kyc_status = serializers.SerializerMethodField()
    aadhaar_last4 = serializers.SerializerMethodField()
    profile = UserProfileSerializer(read_only=True)

    # Editable user fields (PATCH)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email",
            "first_name", "last_name", "full_name",
            "kyc_status", "aadhaar_last4",
            "profile",
        )
        read_only_fields = ("id", "username", "email", "full_name", "kyc_status", "aadhaar_last4", "profile")

    def get_full_name(self, obj):
        fn = (obj.first_name or "").strip()
        ln = (obj.last_name or "").strip()
        return (fn + " " + ln).strip() or obj.username

    def get_kyc_status(self, obj):
        kyc = getattr(obj, "kyc", None)
        return getattr(kyc, "status", KYCSubmission.Status.PENDING) if kyc else KYCSubmission.Status.PENDING

    def get_aadhaar_last4(self, obj):
        kyc = getattr(obj, "kyc", None)
        return getattr(kyc, "aadhaar_last4", None)

    def update(self, instance, validated_data):
        # Only allow first/last name here
        for f in ("first_name", "last_name"):
            if f in validated_data:
                setattr(instance, f, validated_data[f])
        instance.save(update_fields=["first_name", "last_name"])
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": "Incorrect password"})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
