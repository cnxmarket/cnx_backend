from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import exceptions
from marketdata.models_kyc import KYCSubmission

class KycTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)  # sets self.user
        kyc = getattr(self.user, "kyc", None)

        # No submission yet or still pending
        if not kyc or kyc.status == KYCSubmission.Status.PENDING:
            # DRF will serialize this dict into the response body
            raise exceptions.AuthenticationFailed(
                {"code": "KYC_PENDING", "message": "KYC not approved yet."}
            )

        # Explicit rejected
        if kyc.status == KYCSubmission.Status.REJECTED:
            raise exceptions.AuthenticationFailed(
                {"code": "KYC_REJECTED", "message": "KYC rejected. Please resubmit your documents."}
            )

        # Approved → proceed
        return data