# marketdata/admin.py
from django.contrib import admin, messages
from django.utils import timezone

from .models import Order, Fill, LedgerEntry, PositionSnapshot, UserAccount
from .models_admintrades import (
    AdminBroadcastTrade,
    UserTradeGroup,
    AdminTradeApplication,
)
from .services.admin_broadcast_trades import User, apply_closed_admin_trade_on_save
from .admin_kyc import *
from django.contrib import admin, messages
from django.db import transaction
from django import forms
from marketdata.models import WithdrawalRequest, UserAccount
from .models import AlltickConfig
# ------------------ Core models ------------------
admin.site.register(UserAccount)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "position_id", "user_id", "symbol", "side",
        "lots", "price", "status", "created_at",
    )
    list_filter = ("symbol", "status", "side")
    search_fields = ("position_id", "client_id", "id")
    ordering = ("-created_at",)
    autocomplete_fields = ()
    readonly_fields = ()  # add fields here if you want them locked


@admin.register(Fill)
class FillAdmin(admin.ModelAdmin):
    list_display = (
        "id", "order_id", "user_id", "symbol", "side",
        "lots", "price", "realized_pnl", "ts",
    )
    list_filter = ("symbol", "side")
    search_fields = ("order__position_id", "order_id", "symbol")
    ordering = ("-ts",)
    autocomplete_fields = ("order",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "symbol", "kind", "amount", "ref")
    list_filter = ("kind", "symbol")
    search_fields = ("ref", "symbol", "user_id")
    ordering = ("-id",)


@admin.register(PositionSnapshot)
class PositionSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "symbol", "net_lots", "avg_entry", "unreal_pnl", "margin", "mark")
    list_filter = ("symbol",)
    search_fields = ("symbol", "user_id")
    ordering = ("-id",)


# ------------------ Admin Trades ------------------

class AdminTradeApplicationInline(admin.TabularInline):
    model = AdminTradeApplication
    extra = 0
    can_delete = False
    readonly_fields = ("user", "realized", "applied_at")
    fields = ("user", "realized", "applied_at")
    ordering = ("-applied_at",)


@admin.action(description="Set selected trades LIVE (opened_at=now)")
def set_live(modeladmin, request, queryset):
    n = queryset.exclude(status="closed").update(
        status="live",
        opened_at=timezone.now()
    )
    messages.success(request, f"{n} trade(s) set LIVE.")


@admin.action(description="Close & Apply now (affects capital; skips low capital)")
def close_and_apply(modeladmin, request, queryset):
    applied_total = skipped_total = 0
    for t in queryset:
        # Ensure it has the required fields
        if not (t.entry_price and t.exit_price and t.lots and t.side and t.symbol):
            messages.warning(request, f"Trade {t.ref}: missing fields (entry/exit/lots/side/symbol). Skipped.")
            continue
        try:
            res = apply_closed_admin_trade_on_save(t.id)
            applied_total += res.get("applied", 0)
            skipped_total += res.get("skipped", 0)
        except Exception as e:
            messages.error(request, f"Trade {t.ref}: error applying — {e}")
    messages.info(
        request,
        f"Applied to {applied_total} user(s); skipped {skipped_total} (insufficient capital)."
    )


@admin.register(AdminBroadcastTrade)
class AdminBroadcastTradeAdmin(admin.ModelAdmin):
    list_display = (
        "ref", "symbol", "side", "lots",
        "entry_price", "exit_price", "leverage",
        "status", "opened_at", "closed_at",
    )
    list_filter = ("status", "symbol", "side", "leverage")
    search_fields = ("ref", "symbol", "notes")
    filter_horizontal = ("groups",)
    ordering = ("-closed_at", "-opened_at", "-id")

    # Don't apply here (M2M not saved yet)
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    # Apply here (M2M saved already)
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.entry_price and obj.exit_price and obj.lots and obj.side and obj.symbol:
            try:
                res = apply_closed_admin_trade_on_save(obj.id)
                messages.info(
                    request,
                    f"Admin Trade applied. Success: {res['applied']}, "
                    f"Skipped (insufficient capital): {res['skipped']}."
                )
            except Exception as e:
                messages.error(request, f"Error applying trade {obj.ref}: {e}")



@admin.register(UserTradeGroup)
class UserTradeGroupAdmin(admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("users",)


@admin.register(AdminTradeApplication)
class AdminTradeApplicationAdmin(admin.ModelAdmin):
    list_display = ("trade", "user", "realized", "applied_at")
    search_fields = ("trade__ref", "user__username")
    ordering = ("-applied_at",)
    readonly_fields = ("trade", "user", "realized", "applied_at")



from .models_profile import UserProfile
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")


class WithdrawalAdminForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        comment = (cleaned.get("comment") or "").strip()

        # Load the original row to know if it was already finalised
        if self.instance.pk:
            try:
                original = WithdrawalRequest.objects.get(pk=self.instance.pk)
            except WithdrawalRequest.DoesNotExist:
                original = None
            if original and original.status in (WithdrawalRequest.Status.APPROVED, WithdrawalRequest.Status.REJECTED):
                raise forms.ValidationError("This withdrawal has already been processed and cannot be edited.")

        if status == WithdrawalRequest.Status.REJECTED and not comment:
            raise forms.ValidationError("Comment is required when rejecting a request.")

        return cleaned


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    form = WithdrawalAdminForm
    list_display = ("id", "user", "amount", "status", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj: WithdrawalRequest, form, change):
        if not change:
            # Creating: typically status stays 'created'
            return super().save_model(request, obj, form, change)

        # Fetch original to check previous status
        original = WithdrawalRequest.objects.get(pk=obj.pk)
        if original.status in (WithdrawalRequest.Status.APPROVED, WithdrawalRequest.Status.REJECTED):
            messages.error(request, "Already processed; cannot modify.")
            return

        new_status = form.cleaned_data.get("status", obj.status)

        if new_status == WithdrawalRequest.Status.APPROVED:
            with transaction.atomic():
                ua = UserAccount.objects.select_for_update().get(user_id=obj.user_id)
                if obj.amount > ua.balance:
                    messages.error(request, "Insufficient capital at approval time.")
                    return
                ua.balance = ua.balance - obj.amount
                ua.save(update_fields=["balance"])
                obj.status = WithdrawalRequest.Status.APPROVED
                obj.reviewed_by = request.user
                super().save_model(request, obj, form, change)
                messages.success(request, "Withdrawal approved and balance deducted.")
                return

        if new_status == WithdrawalRequest.Status.REJECTED:
            obj.status = WithdrawalRequest.Status.REJECTED
            obj.reviewed_by = request.user
            super().save_model(request, obj, form, change)
            messages.warning(request, "Withdrawal rejected.")
            return

        # Unchanged / still 'created'
        super().save_model(request, obj, form, change)



@admin.register(AlltickConfig)
class AlltickConfigAdmin(admin.ModelAdmin):
    list_display = ('api_key', 'base_rest_url', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('api_key',)
    
    # Optional: Prevent deleting the last config to avoid system breakage
    def has_delete_permission(self, request, obj=None):
        return False