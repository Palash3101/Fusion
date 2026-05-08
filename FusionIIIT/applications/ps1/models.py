from django.db import models
from django.contrib.auth.models import User
from applications.globals.models import Staff, ExtraInfo, DepartmentInfo
from applications.filetracking.models import File
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.validators import MinValueValidator


class LocationChoices(models.TextChoices):
    LHTC = 'SR1', 'LHTC'
    COMPUTER_CENTER = 'SR2', 'Computer Center'
    PANINI_HOSTEL = 'SR3', 'Panini Hostel'
    LAB_COMPLEX = 'SR4', 'Lab complex'
    ADMIN_BLOCK = 'SR5', 'Admin Block'


# Keep legacy Constants class for backward compat with any old references
class Constants:
    Locations = (
        ('SR1', 'LHTC'),
        ('SR2', 'Computer Center'),
        ('SR3', 'Panini Hostel'),
        ('SR4', 'Lab complex'),
        ('SR5', 'Admin Block'),
    )


class IndentStatusChoices(models.TextChoices):
    """T-01: Status choices for soft-cancel functionality"""
    ACTIVE = 'ACTIVE', 'Active'
    CANCELLED = 'CANCELLED', 'Cancelled'
    COMPLETED = 'COMPLETED', 'Completed'
    REJECTED = 'REJECTED', 'Rejected'


class IndentFile(models.Model):
    """
    Enhanced IndentFile model with Assignment 7 requirements:
    - T-01: Soft-cancel with status field
    - T-02: Rejection tracking
    - T-14: SLA deadline tracking
    """
    file_info = models.OneToOneField(File, on_delete=models.CASCADE, primary_key=True)
    indent_name = models.CharField(max_length=250, blank=False, default='Untitled Indent')
    description = models.TextField(blank=True)  # Description of the indent
    head_approval = models.BooleanField(default=False)
    director_approval = models.BooleanField(default=False)
    financial_approval = models.BooleanField(default=False)
    purchased = models.BooleanField(default=False)
    approved_by = models.TextField(blank=True, default="")

    # T-01: Soft-cancel implementation
    status = models.CharField(
        max_length=20,
        choices=IndentStatusChoices.choices,
        default=IndentStatusChoices.ACTIVE
    )
    cancellation_reason = models.TextField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelled_indents'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # T-02: Rejection tracking
    rejection_reason = models.TextField(blank=True, null=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rejected_indents'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    # T-14: SLA deadline tracking (BR-PS-014)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    escalated = models.BooleanField(default=False)
    escalation_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'IndentFile'

    def soft_cancel(self, user, reason):
        """T-01: Soft-cancel method preserving audit trail"""
        self.status = IndentStatusChoices.CANCELLED
        self.cancellation_reason = reason
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.save()

    def reject(self, user, reason):
        """T-02: Rejection method"""
        self.status = IndentStatusChoices.REJECTED
        self.rejection_reason = reason
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.save()


class IndentItem(models.Model):
    """
    Enhanced IndentItem with Assignment 7 validations:
    - T-06: Mandatory field validation
    - T-07: Min value validators
    """
    indent_file = models.ForeignKey(IndentFile, on_delete=models.CASCADE, related_name='items')
    item_name = models.CharField(max_length=250, blank=False)
    quantity = models.IntegerField(blank=False, validators=[MinValueValidator(1)])
    present_stock = models.IntegerField(blank=False)
    estimated_cost = models.IntegerField(
        null=True, blank=False,
        validators=[MinValueValidator(1)]
    )
    purpose = models.CharField(max_length=250, blank=False)
    specification = models.CharField(max_length=250, blank=False)
    item_type = models.CharField(max_length=250, blank=False)
    item_subtype = models.CharField(max_length=250, blank=False, default='computers')
    nature = models.BooleanField(default=False)
    indigenous = models.BooleanField(default=False)
    replaced = models.BooleanField(default=False)
    budgetary_head = models.CharField(max_length=250, blank=False)
    expected_delivery = models.DateField(blank=False)
    sources_of_supply = models.CharField(max_length=250, blank=False)

    class Meta:
        db_table = 'IndentItem'


class Vendor(models.Model):
    """
    T-09: Vendor master model (PSM-UC-019, BR-PS-012)
    Centralized vendor management with validation
    """
    vendor_code = models.CharField(max_length=50, unique=True)
    vendor_name = models.CharField(max_length=250, blank=False)
    contact_person = models.CharField(max_length=250, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    # Vendor validation fields
    is_approved = models.BooleanField(default=False)
    gst_number = models.CharField(max_length=15, blank=True)
    pan_number = models.CharField(max_length=10, blank=True)

    # Performance tracking
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    total_orders = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'Vendor'
        ordering = ['vendor_name']

    def __str__(self):
        return f"{self.vendor_code} - {self.vendor_name}"


class StockEntry(models.Model):
    """
    Enhanced StockEntry with vendor ForeignKey
    T-09: Replace CharField vendor with ForeignKey to Vendor model
    T-16: Asset tagging for capitalization
    """
    item_id = models.OneToOneField(IndentItem, on_delete=models.CASCADE, primary_key=True)
    dealing_assistant_id = models.ForeignKey(ExtraInfo, on_delete=models.CASCADE)

    # T-09: Vendor as ForeignKey
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT,
        related_name='stock_entries'
    )

    current_stock = models.IntegerField(blank=False)
    recieved_date = models.DateField(blank=False)
    bill = models.FileField(blank=False)
    location = models.CharField(
        max_length=100,
        choices=LocationChoices.choices,
        default=LocationChoices.LHTC
    )

    # T-16: Asset tagging (BR-PS-016)
    is_capital_asset = models.BooleanField(default=False)
    capitalization_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=50000.00
    )

    class Meta:
        db_table = 'StockEntry'


class StockItem(models.Model):
    """
    Enhanced StockItem with asset tag support
    T-16: Asset tag field for capital assets (BR-PS-016)
    """
    # this StockEntryId will never change once created; used to get grade/indentfile details.
    StockEntryId = models.ForeignKey(StockEntry, on_delete=models.CASCADE)
    nomenclature = models.CharField(max_length=100, unique=True)
    inUse = models.BooleanField(default=True)

    department = models.ForeignKey(
        DepartmentInfo, on_delete=models.CASCADE, null=True, blank=True)
    location = models.CharField(
        max_length=100,
        choices=LocationChoices.choices,
        default=LocationChoices.LHTC
    )
    isTransferred = models.BooleanField(default=False)

    # T-16: Asset tag for capital assets (BR-PS-016)
    asset_tag = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        db_table = 'StockItem'

    def save(self, *args, **kwargs):
        # Generate nomenclature when saving the StockItem instance
        if not self.nomenclature:
            max_existing_number = StockItem.objects.filter(
                StockEntryId=self.StockEntryId_id).count()
            new_number = max_existing_number + 1
            self.nomenclature = f"{self.StockEntryId.item_id}_{new_number}"

        # T-16: Auto-generate asset tag for capital assets
        if self.StockEntryId.is_capital_asset and not self.asset_tag:
            self.asset_tag = f"ASSET-{timezone.now().year}-{self.id or 'NEW'}"

        super().save(*args, **kwargs)


class StockReservation(models.Model):
    """
    T-13: Stock reservation model (BR-PS-013)
    Tracks reserved stock to prevent double allocation
    """
    stock_item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='reservations')
    indent_file = models.ForeignKey(IndentFile, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    reserved_by = models.ForeignKey(User, on_delete=models.CASCADE)
    reserved_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'StockReservation'
        ordering = ['-reserved_at']


# this table will be used to keep a track of all the stockTransfer things.
class StockTransfer(models.Model):
    indent_file = models.ForeignKey(IndentFile, on_delete=models.CASCADE)

    src_dept = models.ForeignKey(
        DepartmentInfo, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dept_src_transfers')
    dest_dept = models.ForeignKey(
        DepartmentInfo, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dept_dest_transfers')

    stockItem = models.ForeignKey(StockItem, on_delete=models.CASCADE)
    src_location = models.CharField(
        max_length=100,
        choices=LocationChoices.choices,
        default=LocationChoices.LHTC
    )
    dest_location = models.CharField(
        max_length=100,
        choices=LocationChoices.choices,
        default=LocationChoices.COMPUTER_CENTER
    )
    dateTime = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'StockTransfer'


class GoodsReceivedNote(models.Model):
    """
    T-04: GRN/Delivery Confirmation model (PSM-UC-002, BR-PS-009, BR-PS-017)
    Required before invoice release
    """
    grn_number = models.CharField(max_length=100, unique=True)
    indent_file = models.ForeignKey(IndentFile, on_delete=models.CASCADE, related_name='grns')
    stock_entry = models.ForeignKey(StockEntry, on_delete=models.CASCADE, related_name='grns')

    # Confirmation details
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='received_grns'
    )
    confirmed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='confirmed_grns'
    )
    received_date = models.DateTimeField(auto_now_add=True)
    confirmed_date = models.DateTimeField(null=True, blank=True)

    # Quality check
    quantity_received = models.IntegerField(validators=[MinValueValidator(1)])
    quantity_accepted = models.IntegerField(validators=[MinValueValidator(0)])
    quality_check_passed = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)

    # Discrepancy tracking (T-05)
    has_discrepancy = models.BooleanField(default=False)
    discrepancy_details = models.TextField(blank=True)

    # Invoice release control (BR-PS-009)
    invoice_release_approved = models.BooleanField(default=False)

    class Meta:
        db_table = 'GoodsReceivedNote'
        ordering = ['-received_date']

    def save(self, *args, **kwargs):
        if not self.grn_number:
            # Auto-generate GRN number
            year = timezone.now().year
            count = GoodsReceivedNote.objects.filter(
                grn_number__startswith=f'GRN-{year}'
            ).count() + 1
            self.grn_number = f'GRN-{year}-{count:05d}'
        super().save(*args, **kwargs)


class ProductReturn(models.Model):
    """
    T-05: Product Return & Claims Processing (PSM-WF-003, UC-020, BR-PS-018, BR-PS-019)
    Entire return workflow implementation
    """
    class ReturnStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        REFUNDED = 'REFUNDED', 'Refunded'
        REPLACED = 'REPLACED', 'Replaced'

    return_number = models.CharField(max_length=100, unique=True)
    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name='returns')
    stock_entry = models.ForeignKey(StockEntry, on_delete=models.CASCADE, related_name='returns')

    # Return details
    return_reason = models.TextField(blank=False)
    quantity_returned = models.IntegerField(validators=[MinValueValidator(1)])
    return_initiated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='initiated_returns'
    )
    return_date = models.DateTimeField(auto_now_add=True)

    # Discrepancy flag (BR-PS-018)
    has_discrepancy = models.BooleanField(default=True)
    discrepancy_type = models.CharField(max_length=100, blank=True)
    discrepancy_description = models.TextField(blank=True)

    # Status and workflow
    status = models.CharField(
        max_length=20,
        choices=ReturnStatus.choices,
        default=ReturnStatus.PENDING
    )

    # Resolution
    resolution_type = models.CharField(
        max_length=20,
        choices=[
            ('REFUND', 'Refund'),
            ('REPLACE', 'Replace'),
            ('REJECT', 'Reject Claim')
        ],
        blank=True
    )
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_returns'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_remarks = models.TextField(blank=True)

    # Invoice hold (BR-PS-018)
    invoice_hold = models.BooleanField(default=True)
    invoice_hold_released = models.BooleanField(default=False)

    class Meta:
        db_table = 'ProductReturn'
        ordering = ['-return_date']

    def save(self, *args, **kwargs):
        if not self.return_number:
            year = timezone.now().year
            count = ProductReturn.objects.filter(
                return_number__startswith=f'RET-{year}'
            ).count() + 1
            self.return_number = f'RET-{year}-{count:05d}'
        super().save(*args, **kwargs)


class Tender(models.Model):
    """
    T-08: Tender management model (PSM-UC-022, BR-PS-008)
    Required for high-value competitive procurement
    """
    class TenderStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        BIDDING = 'BIDDING', 'Bidding Open'
        EVALUATION = 'EVALUATION', 'Under Evaluation'
        AWARDED = 'AWARDED', 'Awarded'
        CANCELLED = 'CANCELLED', 'Cancelled'

    tender_number = models.CharField(max_length=100, unique=True)
    indent_file = models.ForeignKey(IndentFile, on_delete=models.CASCADE, related_name='tenders')

    # Tender details
    title = models.CharField(max_length=250, blank=False)
    description = models.TextField(blank=False)
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2)

    # Dates
    publish_date = models.DateTimeField(null=True, blank=True)
    bid_submission_deadline = models.DateTimeField()
    bid_opening_date = models.DateTimeField()

    # Status
    status = models.CharField(
        max_length=20,
        choices=TenderStatus.choices,
        default=TenderStatus.DRAFT
    )

    # Award
    awarded_to = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='awarded_tenders'
    )
    awarded_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    awarded_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Tender'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.tender_number:
            year = timezone.now().year
            count = Tender.objects.filter(
                tender_number__startswith=f'TND-{year}'
            ).count() + 1
            self.tender_number = f'TND-{year}-{count:05d}'
        super().save(*args, **kwargs)


class TenderBid(models.Model):
    """
    T-08: Tender bid submission tracking
    """
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE, related_name='bids')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='bids')

    bid_amount = models.DecimalField(max_digits=12, decimal_places=2)
    bid_document = models.FileField(upload_to='tender_bids/', blank=True)
    technical_compliance = models.BooleanField(default=False)

    submitted_at = models.DateTimeField(auto_now_add=True)
    evaluated = models.BooleanField(default=False)
    evaluation_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    evaluation_remarks = models.TextField(blank=True)

    is_winner = models.BooleanField(default=False)

    class Meta:
        db_table = 'TenderBid'
        unique_together = ['tender', 'vendor']
        ordering = ['bid_amount']


class AuditLog(models.Model):
    """
    T-23: Audit trail for all critical operations (UC-014)
    """
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)
    entity_id = models.IntegerField()
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'AuditLog'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['entity_type', 'entity_id']),
        ]


# Signals
@receiver(post_save, sender=StockEntry)
def create_stock_items(sender, instance, created, **kwargs):
    """Auto-create StockItems when StockEntry is created"""
    if created:
        department = instance.item_id.indent_file.file_info.uploader.department
        current_stock = int(instance.current_stock)

        # T-16: Check if capital asset based on threshold
        total_cost = instance.item_id.estimated_cost or 0
        is_capital = total_cost >= instance.capitalization_threshold
        instance.is_capital_asset = is_capital
        instance.save()

        for i in range(current_stock):
            StockItem.objects.create(
                StockEntryId=instance,
                location=instance.location,
                department=department
            )