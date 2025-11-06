from django.db import models
from django.contrib.auth.models import User
from .models_admintrades import *


class Order(models.Model):
    user_id = models.IntegerField(db_index=True)
    position_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    symbol = models.CharField(max_length=32, db_index=True)
    side = models.CharField(max_length=4)  # Buy/Sell
    lots = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=6, null=True)  # limit/stop or exec px for market
    type = models.CharField(max_length=16, default="market")  # market/limit/stop
    status = models.CharField(max_length=16, default="filled")  # new/open/filled/canceled/partially_filled
    client_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)  # idempotency
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Fill(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fills")
    user_id = models.IntegerField(db_index=True)
    symbol = models.CharField(max_length=32, db_index=True)
    side = models.CharField(max_length=4)  # Buy/Sell
    lots = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=6)
    realized_pnl = models.DecimalField(max_digits=28, decimal_places=8, default=0)
    ts = models.DateTimeField(auto_now_add=True)

class LedgerEntry(models.Model):
    user_id = models.IntegerField(db_index=True)
    symbol = models.CharField(max_length=32, null=True, blank=True)
    kind = models.CharField(max_length=32)  # realized_pnl, fee, deposit, withdrawal, adj
    amount = models.DecimalField(max_digits=28, decimal_places=8)
    ref = models.CharField(max_length=64, null=True, blank=True)
    ts = models.DateTimeField(auto_now_add=True)

class PositionSnapshot(models.Model):
    user_id = models.IntegerField(db_index=True)
    symbol = models.CharField(max_length=32, db_index=True)
    net_lots = models.DecimalField(max_digits=20, decimal_places=6)
    avg_entry = models.DecimalField(max_digits=20, decimal_places=6)
    unreal_pnl = models.DecimalField(max_digits=28, decimal_places=8)
    margin = models.DecimalField(max_digits=28, decimal_places=8)
    mark = models.DecimalField(max_digits=20, decimal_places=6)
    ts = models.DateTimeField(auto_now_add=True)


class UserAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    used_margin = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    unrealized_pnl = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    # Add other fields as needed

    @property
    def equity(self):
        """Equity = Balance + Unrealized PnL"""
        return self.balance + self.unrealized_pnl

    @property
    def free_margin(self):
        """Free Margin = Equity - Used Margin"""
        return self.equity - self.used_margin

    # Make sure any existing free_margin() method is a property, not a function that returns a method
    @property
    def margin_level(self):
        """Margin Level = (Equity / Used Margin) * 100% if used_margin > 0"""
        used_margin = self.used_margin if self.used_margin > 0 else Decimal('1.0000')
        return float(self.equity / used_margin) if self.equity > 0 and used_margin > 0 else float('inf')

    def __str__(self):
        return f"User {self.user.username} Account: Balance={self.balance}, Equity={self.equity}"


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    comment = models.TextField(blank=True)  # admin remark, shown to user if rejected
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="withdrawals_reviewed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Withdrawal #{self.id} {self.user} {self.amount} {self.status}"