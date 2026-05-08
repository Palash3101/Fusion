import json
import secrets
import string

from django.conf import settings
from django.db import models
from django.utils import timezone

from psmodule.accounts.models import DepartmentInfo, ExtraInfo


class JSONTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return []
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return []

    def to_python(self, value):
        if value in (None, ""):
            return []
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return []
        return value

    def get_prep_value(self, value):
        if value in (None, ""):
            return "[]"
        if isinstance(value, str):
            return value
        return json.dumps(value)


class ActingRole(models.TextChoices):
    EMPLOYEE = "EMPLOYEE", "Employee"
    DEPADMIN = "DEPADMIN", "Department Admin"
    PS_ADMIN = "PS_ADMIN", "PS Admin"
    HOD = "HOD", "Head of Department"
    REGISTRAR = "REGISTRAR", "Registrar"
    DIRECTOR = "DIRECTOR", "Director"


class StockCheckStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    PARTIAL = "PARTIAL", "Partial"
    NOT_AVAILABLE = "NOT_AVAILABLE", "Not Available"


class StoreItem(models.Model):
    name = models.CharField(max_length=255, unique=True)
    unit = models.CharField(max_length=50, default="nos")  # e.g., nos/kg/ltr

    def __str__(self) -> str:
        return self.name


class CurrentStock(models.Model):
    item = models.OneToOneField(
        StoreItem, on_delete=models.CASCADE, related_name="stock"
    )
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.item}: {self.quantity}"


class Indent(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_HOD_REVIEW = "UNDER_HOD_REVIEW", "Under HOD Review"
        STOCK_CHECKED = "STOCK_CHECKED", "Stock Checked"
        INTERNAL_ISSUED = "INTERNAL_ISSUED", "Internal Issued"
        EXTERNAL_PROCUREMENT = "EXTERNAL_PROCUREMENT", "External Procurement"
        FORWARDED_TO_DIRECTOR = "FORWARDED_TO_DIRECTOR", "Forwarded to Director"
        APPROVED_BY_DEP_ADMIN = "APPROVED_BY_DEP_ADMIN", "Approved by Dept Admin"
        APPROVED = "APPROVED", "Approved"
        STOCKED = "STOCKED", "Stocked"
        REJECTED = "REJECTED", "Rejected"
        FORWARDED = "FORWARDED", "Forwarded"
        BIDDING = "BIDDING", "Bidding"
        PURCHASED = "PURCHASED", "Purchased"
        STOCK_ENTRY = "STOCK_ENTRY", "Stock Entry"
        STOCK_ALLOCATED = "STOCK_ALLOCATED", "Stock Allocated"

    class ProcurementType(models.TextChoices):
        INTERNAL = "INTERNAL", "Internal Stock"
        EXTERNAL = "EXTERNAL", "External Procurement"

    class UrgencyLevel(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    indenter = models.ForeignKey(
        ExtraInfo, on_delete=models.PROTECT, related_name="indents"
    )
    department = models.ForeignKey(
        DepartmentInfo, on_delete=models.PROTECT, related_name="indents"
    )
    purpose = models.CharField(max_length=255)
    justification = models.TextField(blank=True, default="")
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT
    )
    stock_available = models.BooleanField(default=False)
    procurement_type = models.CharField(
        max_length=20,
        choices=ProcurementType.choices,
        null=True,
        blank=True,
    )
    delivery_confirmed = models.BooleanField(default=False)
    current_approver = models.ForeignKey(
        ExtraInfo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pending_indents",
    )

    public_reference_id = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
    )
    date_of_request = models.DateField(default=timezone.localdate)
    designation = models.CharField(max_length=200, blank=True, default="")
    contacts = JSONTextField(default=list, blank=True)
    why_requirement_needed = models.TextField(blank=True, default="")
    urgency_level = models.CharField(
        max_length=20,
        choices=UrgencyLevel.choices,
        default=UrgencyLevel.MEDIUM,
    )
    expected_usage = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Indent #{self.id} by {self.indenter}"

    def _generate_public_reference_id(self) -> str:
        digits = string.digits
        d = timezone.localdate().strftime("%Y%m%d")
        for _ in range(20):
            suffix = "".join(secrets.choice(digits) for _ in range(6))
            candidate = f"IND-{d}-{suffix}"
            if not Indent.objects.filter(public_reference_id=candidate).exists():
                return candidate
        return f"IND-{d}-{secrets.token_hex(4).upper()}"

    def save(self, *args, **kwargs):
        if not self.public_reference_id:
            self.public_reference_id = self._generate_public_reference_id()
        super().save(*args, **kwargs)


class IndentItem(models.Model):
    indent = models.ForeignKey(Indent, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(
        StoreItem,
        on_delete=models.PROTECT,
        related_name="indent_lines",
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField()
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    line_name = models.CharField(max_length=255, blank=True, default="")
    line_description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=120, blank=True, default="")
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["indent", "item"],
                condition=models.Q(item__isnull=False),
                name="uniq_item_per_indent_when_item_set",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.indent_id}: {self.item_id} x {self.quantity}"


class IndentDocument(models.Model):
    indent = models.ForeignKey(
        Indent, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to="indent_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"IndentDoc {self.id} for {self.indent_id}"


class IndentAudit(models.Model):
    indent = models.ForeignKey(
        Indent, on_delete=models.CASCADE, related_name="audit_events"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    acting_role = models.CharField(max_length=50)  # EMPLOYEE/HOD
    action = models.CharField(max_length=50)  # SUBMIT/APPROVE/REJECT/FORWARD
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.indent_id} {self.action} by {self.user_id}"


class StockEntry(models.Model):
    indent = models.ForeignKey(
        Indent, on_delete=models.PROTECT, related_name="stock_entries"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_entries"
    )
    acting_role = models.CharField(max_length=50)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"StockEntry #{self.id} for indent {self.indent_id}"


class StockEntryItem(models.Model):
    stock_entry = models.ForeignKey(
        StockEntry, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(
        StoreItem, on_delete=models.PROTECT, related_name="stock_entry_lines"
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stock_entry", "item"], name="uniq_item_per_stock_entry"
            ),
        ]

    def __str__(self) -> str:
        return f"StockEntry {self.stock_entry_id}: {self.item_id} x {self.quantity}"


class StockAllocation(models.Model):
    indent = models.ForeignKey(
        Indent, on_delete=models.PROTECT, related_name="stock_allocations"
    )
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_allocations"
    )
    acting_role = models.CharField(max_length=50)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"StockAllocation #{self.id} for indent {self.indent_id}"


class StockAllocationItem(models.Model):
    stock_allocation = models.ForeignKey(
        StockAllocation, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(
        StoreItem, on_delete=models.PROTECT, related_name="stock_allocation_lines"
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stock_allocation", "item"], name="uniq_item_per_stock_allocation"
            ),
        ]

    def __str__(self) -> str:
        return f"StockAllocation {self.stock_allocation_id}: {self.item_id} x {self.quantity}"
