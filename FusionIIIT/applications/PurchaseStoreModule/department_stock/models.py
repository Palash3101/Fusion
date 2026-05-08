from django.conf import settings
from django.db import models


class Stock(models.Model):
    stock_name = models.CharField(max_length=255)
    department = models.CharField(max_length=50, db_index=True)
    quantity = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.stock_name} ({self.department})"


class TransferRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name="transfer_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfer_requests",
    )
    requested_from = models.CharField(max_length=50)
    requested_quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Request {self.id} {self.stock} -> {self.requested_from} [{self.status}]"


class TransferLog(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name="transfer_logs")
    from_department = models.CharField(max_length=50)
    to_department = models.CharField(max_length=50)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_transfers",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.stock} {self.from_department}->{self.to_department} by {self.approved_by.username}"
