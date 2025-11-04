# marketdata/views_admintrades.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet
from .models_admintrades import AdminBroadcastTrade
from .serializers_admintrades import AdminTradePublicSerializer

class MyAdminTradesViewSet(ReadOnlyModelViewSet):
    serializer_class = AdminTradePublicSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        u = self.request.user
        return (AdminBroadcastTrade.objects
                .filter(groups__users=u, status="closed")
                .distinct()
                .order_by("-closed_at", "-opened_at"))