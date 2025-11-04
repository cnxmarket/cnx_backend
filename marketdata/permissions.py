# marketdata/permissions.py
from rest_framework.permissions import BasePermission
from .models_kyc import KYCSubmission

class IsKYCVerified(BasePermission):
    message = "KYC verification required."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        kyc = getattr(request.user, "kyc", None)
        return bool(kyc and kyc.status == KYCSubmission.Status.APPROVED)
