# marketdata/views_kyc.py
from rest_framework import status, permissions, generics, views
from rest_framework.response import Response
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers_kyc import (
    RegisterSerializer,
    KYCSubmitSerializer,
    KYCStatusSerializer,
)
from .models_kyc import KYCSubmission

import hashlib

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    Public registration. Does NOT log the user in.
    Creates the user and an (optional) empty KYC row.
    Frontend should redirect to /kyc to upload docs.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        user = User.objects.create_user(
            username=data["username"],
            email=data["email"],
            password=data["password"],
        )
        KYCSubmission.objects.get_or_create(user=user)


class KYCSubmitView(generics.CreateAPIView):
    """
    Authenticated KYC submit (if you prefer users to be logged in).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = KYCSubmitSerializer


class KYCStatusView(views.APIView):
    """
    Returns current user's KYC status.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        kyc = getattr(request.user, "kyc", None)
        if not kyc:
            return Response({"status": "pending"}, status=200)
        return Response(KYCStatusSerializer(kyc).data, status=200)


# ---- Optional: Public KYC submit (no login, ties by email) -----------------
@method_decorator(csrf_exempt, name="dispatch")
class KYCSubmitPublicView(views.APIView):
    """
    Public KYC submit to support: register -> upload KYC -> wait approval -> then login.
    Expects multipart/form-data: email, aadhaar_number (12 digits), doc_front, doc_back
    """
    # ⬇️ No SessionAuthentication here, so CSRF is not re-enforced by DRF
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    # Explicitly handle multipart/form-data
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        aadhaar_number = (request.data.get("aadhaar_number") or "").strip()
        doc_front = request.FILES.get("doc_front")
        doc_back = request.FILES.get("doc_back")

        if not email or not aadhaar_number or not doc_front or not doc_back:
            return Response(
                {"error": "email, aadhaar_number, doc_front, doc_back are required"},
                status=400,
            )
        if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
            return Response({"error": "Invalid Aadhaar number"}, status=400)

        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"error": "No user with this email"}, status=400)

        # Basic file validation
        for k, f in (("doc_front", doc_front), ("doc_back", doc_back)):
            if getattr(f, "content_type", "") not in (
                "image/jpeg", "image/png", "image/heic", "image/heif",
            ):
                return Response({k: "Unsupported file type"}, status=400)
            if f.size > 5 * 1024 * 1024:
                return Response({k: "File too large (max 5MB)"}, status=400)

        kyc, _ = KYCSubmission.objects.update_or_create(
            user=user,
            defaults=dict(
                aadhaar_last4=aadhaar_number[-4:],
                aadhaar_hash=hashlib.sha256(aadhaar_number.encode()).hexdigest(),
                doc_front=doc_front,
                doc_back=doc_back,
                status=KYCSubmission.Status.PENDING,
                reviewed_at=None,
            ),
        )
        return Response({"status": "pending"}, status=201)