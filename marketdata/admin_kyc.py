# marketdata/admin_kyc.py
from django.contrib import admin
from django.utils import timezone
from .models_kyc import KYCSubmission

@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "submitted_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email", "aadhaar_last4")
    readonly_fields = ("submitted_at", "reviewed_at")

    actions = ["approve_selected", "reject_selected"]

    def approve_selected(self, request, queryset):
        n = queryset.update(status=KYCSubmission.Status.APPROVED, reviewed_at=timezone.now())
        self.message_user(request, f"Approved {n} KYC(s).")
    approve_selected.short_description = "Approve selected KYC"

    def reject_selected(self, request, queryset):
        n = queryset.update(status=KYCSubmission.Status.REJECTED, reviewed_at=timezone.now())
        self.message_user(request, f"Rejected {n} KYC(s).")
    reject_selected.short_description = "Reject selected KYC"
