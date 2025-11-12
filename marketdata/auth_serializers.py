from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import exceptions
from marketdata.models_kyc import KYCSubmission
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import exceptions
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class KycTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Allows login with either username or email + password, then enforces KYC gates.
    Accepted payloads:
      { "username": "...", "password": "..." }
      { "email": "...",    "password": "..." }
      { "identifier": "...", "password": "..." }  # either username or email
    """

    # add flexible input fields
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # keep the original username field (usually "username")
        username_field = self.username_field
        # make sure our serializer also accepts "email" and "identifier"
        self.fields.setdefault("email", self.fields[username_field].__class__(required=False, allow_blank=True))
        self.fields.setdefault("identifier", self.fields[username_field].__class__(required=False, allow_blank=True))

    def validate(self, attrs):
        username_field = self.username_field          # e.g., "username"
        identifier = (
            attrs.get("identifier")
            or attrs.get("email")
            or attrs.get(username_field)
        )

        # If client sent email or generic identifier, map it to the real username field
        # so the parent validate() can authenticate normally.
        if identifier and not attrs.get(username_field):
            # Try to find a user by username or email (case-insensitive)
            user = User.objects.filter(
                Q(**{username_field: identifier}) | Q(email__iexact=identifier)
            ).only(username_field).first()

            if user:
                # populate the field SimpleJWT expects
                attrs[username_field] = getattr(user, username_field)
            else:
                # fall back: set it anyway; parent will fail auth cleanly
                attrs[username_field] = identifier

        # Let SimpleJWT authenticate and build the token (sets self.user)
        data = super().validate(attrs)

        # ----- KYC checks -----
        kyc = getattr(self.user, "kyc", None)

        if not kyc or kyc.status == KYCSubmission.Status.PENDING:
            # respond with structured body + 401
            raise exceptions.AuthenticationFailed(
                {"code": "KYC_PENDING", "message": "KYC not approved yet."}
            )

        if kyc.status == KYCSubmission.Status.REJECTED:
            raise exceptions.AuthenticationFailed(
                {"code": "KYC_REJECTED", "message": "KYC rejected. Please resubmit your documents."}
            )

        return data