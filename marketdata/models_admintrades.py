# marketdata/models_admintrades.py
from django.conf import settings
from django.db import models
import uuid

class UserTradeGroup(models.Model):
    name = models.CharField(max_length=64, unique=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="trade_groups")

    def __str__(self): return self.name


class AdminBroadcastTrade(models.Model):
    SIDE_CHOICES = (("Buy","Buy"),("Sell","Sell"))
    STATUS_CHOICES = (("draft","Draft"),("live","Live"),("closed","Closed"))

    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)              # human or uuid
    symbol = models.CharField(max_length=24)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    lots = models.DecimalField(max_digits=12, decimal_places=4)
    entry_price = models.DecimalField(max_digits=18, decimal_places=6)
    exit_price = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    leverage = models.IntegerField(default=500)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    groups = models.ManyToManyField(UserTradeGroup, related_name="trades", blank=True)

    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    # idempotency guard when applying capital
    applied_to_user_ids = models.JSONField(default=list, blank=True)

    def __str__(self): return f"{self.ref} {self.symbol} {self.side}"


class AdminTradeApplication(models.Model):
    trade = models.ForeignKey(AdminBroadcastTrade, on_delete=models.CASCADE, related_name="applications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    realized = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("trade", "user")  # idempotent per user