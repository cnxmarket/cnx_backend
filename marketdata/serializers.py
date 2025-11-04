# backend/marketdata/serializers.py
from rest_framework import serializers
from .models import Order, Fill

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