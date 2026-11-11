from django.conf import settings
from django.db import models

class Wallet(models.Model):
    class RegistrationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        REGISTERED = "registered", "Registered"
        FAILED = "failed", "Failed"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet"
    )

    address = models.CharField(
        max_length=44,
        unique=True,
        null=True,
        blank=True
    )

    public_key = models.CharField(
        max_length=64,
        blank=True
    )

    registration_status = models.CharField(
        max_length=20,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.PENDING,
        db_index=True
    )

    registration_tx_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.user.username} - {self.address or 'No address'}"
