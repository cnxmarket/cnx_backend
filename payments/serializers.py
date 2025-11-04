from __future__ import annotations
import io, base64, qrcode
from decimal import Decimal
from django.conf import settings
from rest_framework import serializers
from .models import CryptoDepositMethod, UpiDepositRequest

class CryptoDepositMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = CryptoDepositMethod
        fields = [
            "id",
            "name",
            "network",
            "address",
            "min_amount",
            "max_amount",
            "status",
            "qr_url",
            "created_at",
        ]


class UpiRequestCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payer_vpa = serializers.CharField(max_length=120)
    note = serializers.CharField(max_length=160, required=False, allow_blank=True)

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        if v < 10:
            raise serializers.ValidationError("Minimum UPI deposit is ₹10.")
        return v


class UpiRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = UpiDepositRequest
        fields = [
            "id", "amount", "payer_vpa", "note",
            "status", "created_at", "updated_at",
        ]


class UpiDepositRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = UpiDepositRequest
        fields = (
            "id", "amount", "payer_vpa", "note", "status",
            "created_at", "updated_at",
        )