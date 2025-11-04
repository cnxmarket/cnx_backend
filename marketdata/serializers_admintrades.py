# marketdata/serializers_admintrades.py
from rest_framework import serializers
from .models_admintrades import AdminBroadcastTrade, AdminTradeApplication

class AdminTradePublicSerializer(serializers.ModelSerializer):
    closed_at = serializers.DateTimeField(allow_null=True)
    class Meta:
        model = AdminBroadcastTrade
        fields = ("ref","symbol","side","lots","entry_price","exit_price","status","opened_at","closed_at","notes")


class AdminTradePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminBroadcastTrade
        fields = (
            "ref",
            "symbol",
            "side",
            "lots",
            "leverage",
            "entry_price",
            "exit_price",
            "status",
            "opened_at",
            "closed_at",
            "notes",
        )