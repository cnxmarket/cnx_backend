# marketdata/admin_actions.py
from django.utils import timezone
from django.contrib import messages
from .models_admintrades import AdminBroadcastTrade
from .services.admin_broadcast_trades import apply_close_broadcast_trade

@admin.action(description="Set selected trades LIVE (opened_at=now)")
def set_live(modeladmin, request, queryset):
    updated = queryset.update(status="live", opened_at=timezone.now())
    messages.success(request, f"{updated} trade(s) are live now.")

@admin.action(description="Close & apply capital effect")
def close_and_apply(modeladmin, request, queryset):
    for t in queryset:
        if t.exit_price:
            t.status = "live"  # ensure in correct state
            t.save(update_fields=["status"])
            apply_close_broadcast_trade(t.id)
    messages.success(request, "Applied capital effects for closable trades.")
