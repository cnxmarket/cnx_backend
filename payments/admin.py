from django.contrib import admin
from .models import CryptoDepositMethod, UpiDepositRequest


@admin.register(CryptoDepositMethod)
class CryptoDepositMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "network", "address", "status", "min_amount", "max_amount", "created_at")
    list_filter = ("status", "name", "network")
    search_fields = ("address", "network")


@admin.register(UpiDepositRequest)
class UpiDepositRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount", "payer_vpa", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email", "payer_vpa", "utr", "remarks")
    readonly_fields = ("created_at", "updated_at")
