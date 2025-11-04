from __future__ import annotations
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class CryptoDepositMethod(models.Model):
    """
    Catalog row for on-chain USDT (or other coins) deposit endpoints.
    """
    STATUS_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
    ]
    name = models.CharField(max_length=32, default="USDT")  # e.g., USDT
    network = models.CharField(max_length=32, blank=True)   # e.g., TRC20, BEP20, ERC20
    address = models.CharField(max_length=128)
    min_amount = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    max_amount = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="online")
    # If you store a hosted PNG of the address QR (optional)
    qr_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "network", "address")
        ordering = ["name", "network"]

    def __str__(self):
        n = f"{self.name}"
        if self.network:
            n += f" {self.network}"
        return n


class UpiDepositRequest(models.Model):
    """
    A user-submitted UPI deposit request (no merchant QR/deeplink).
    Ops verifies externally and marks approved in admin.
    """
    STATUS_CHOICES = [
        ("created", "Created"),
        ("approved", "Approved / Credited"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="upi_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payer_vpa = models.CharField(max_length=120, help_text="User's UPI ID (VPA)")
    note = models.CharField(max_length=160, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    utr = models.CharField(max_length=64, blank=True)        # optional reconciliation
    remarks = models.CharField(max_length=240, blank=True)   # internal notes (ops)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"UPI #{self.id} · {self.user} · ₹{self.amount} · {self.status}"