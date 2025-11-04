from __future__ import annotations
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils.timezone import localtime
from .serializers import UpiDepositRequestListSerializer
from .pagination import SmallPageNumberPagination
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated


from .models import CryptoDepositMethod, UpiDepositRequest
from .serializers import (
    CryptoDepositMethodSerializer,
    UpiRequestCreateSerializer,
    UpiRequestSerializer,
)
from .telegram import notify_telegram


class IsAuthed(permissions.IsAuthenticated):
    pass


class CryptoMethodListView(generics.ListAPIView):
    """GET /api/deposit/crypto-methods/"""
    permission_classes = [IsAuthed]
    serializer_class = CryptoDepositMethodSerializer

    def get_queryset(self):
        qs = CryptoDepositMethod.objects.all()
        only_online = self.request.query_params.get("online")
        if only_online in ("1", "true", "True"):
            qs = qs.filter(status="online")
        return qs


class CreateUpiRequestView(APIView):
    """
    POST /api/deposit/upi/request/
    body: { amount, payer_vpa, note? }
    Returns newly created UpiDepositRequest (status=created)
    Also sends a Telegram alert.
    """
    permission_classes = [IsAuthed]

    def post(self, request):
        ser = UpiRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        intent = UpiDepositRequest.objects.create(
            user=request.user,
            amount=ser.validated_data["amount"],
            payer_vpa=ser.validated_data["payer_vpa"].strip(),
            note=ser.validated_data.get("note", "").strip(),
            status="created",
        )

        # Telegram alert
        ts = localtime(intent.created_at).strftime("%Y-%m-%d %H:%M:%S")
        uname = request.user.get_username()
        full = getattr(request.user, "get_full_name", lambda: "")() or uname
        msg = (
            f"💸 <b>New UPI Deposit Request</b>\n"
            f"👤 User: {full} (@{uname})\n"
            f"💰 Amount: ₹{intent.amount}\n"
            f"🏷️ Payer VPA: <code>{intent.payer_vpa}</code>\n"
            f"🕒 Time: {ts}\n"
            f"🧾 Note: {intent.note or '-'}\n"
            f"🔗 Admin: change status to <b>approved</b>/<b>rejected</b> after processing."
        )
        notify_telegram(msg)

        return Response(UpiRequestSerializer(intent).data, status=status.HTTP_201_CREATED)


class MyUpiDepositRequestListView(ListAPIView):
    """
    GET /api/deposit/upi/requests/?page=1&page_size=10
    Returns only the authenticated user's UPI requests, newest first.
    """
    serializer_class = UpiDepositRequestListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SmallPageNumberPagination

    def get_queryset(self):
        return UpiDepositRequest.objects.filter(user=self.request.user).order_by("-created_at")