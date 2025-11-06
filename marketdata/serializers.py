# backend/marketdata/serializers.py
from rest_framework import serializers
from .models import Order, Fill
from marketdata.models import WithdrawalRequest, UserAccount

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = "__all__"

class FillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fill
        fields = "__all__"


class ClosedTradeSerializer(serializers.Serializer):
    pos_id = serializers.CharField(source="ref")
    symbol = serializers.CharField()
    realized = serializers.DecimalField(max_digits=20, decimal_places=6)
    last_ts = serializers.DateTimeField()


class WithdrawalRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = ["id", "amount", "status", "comment", "created_at"]
        read_only_fields = ["id", "status", "comment", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        ua = UserAccount.objects.filter(user_id=user.id).first()
        if not ua:
            raise serializers.ValidationError("User account not found.")
        if attrs["amount"] > ua.balance:
            raise serializers.ValidationError("Withdrawal amount cannot exceed available capital.")
        return attrs

    def create(self, validated):
        return WithdrawalRequest.objects.create(user=self.context["request"].user, **validated)


class WithdrawalRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = ["id", "amount", "status", "comment", "created_at", "updated_at"]