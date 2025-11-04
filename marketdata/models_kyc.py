# marketdata/models_kyc.py
from django.conf import settings
from django.db import models

class KYCSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kyc")
    aadhaar_last4 = models.CharField(max_length=4)          # store only last 4 (privacy)
    aadhaar_hash = models.CharField(max_length=128)          # hash(full number) if you need de-dup checks
    doc_front = models.ImageField(upload_to="kyc/aadhaar/front/")
    doc_back  = models.ImageField(upload_to="kyc/aadhaar/back/")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_note = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"KYC {self.user_id} [{self.status}]"
