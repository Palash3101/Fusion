"""
services_assignment7_additions.py — PS1 Module Assignment 7 Enhancements

New service functions for Assignment 7 requirements.
These should be integrated into the main services.py file.
"""

from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Sum

from applications.ps1.models import (
    IndentFile, IndentItem, Vendor, GoodsReceivedNote,
    ProductReturn, Tender, TenderBid, StockReservation,
    StockEntry, StockItem, AuditLog, IndentStatusChoices
)
from applications.ps1.constants import (
    COST_THRESHOLD_DEPT_HEAD, COST_THRESHOLD_REGISTRAR,
    TENDER_THRESHOLD, SLA_DEPT_ADMIN_HOURS, SLA_HOD_HOURS,
    DUPLICATE_DETECTION_WINDOW_HOURS, ASSET_CAPITALIZATION_THRESHOLD
)
from notification.views import office_module_notif as purchase_notif


# ── T-01: Soft Cancel Services ────────────────────────────────────────────────

def service_soft_cancel_indent(indent_id, user, reason):
    """
    T-01: Soft-cancel indent (BR-PS-007)
    Preserves audit trail, doesn't hard delete
    """
    indent = get_object_or_404(IndentFile, file_info_id=indent_id)
    
    # Guard: Check if already cancelled
    if indent.status == IndentStatusChoices.CANCELLED:
        return None, 'already_cancelled'
    
    # Guard: Check if already completed/purchased
    if indent.status == IndentStatusChoices.COMPLETED or indent.purchased:
        return None, 'cannot_cancel_completed'
    
    indent.soft_cancel(user, reason)
    
    # T-23: Audit log
    _create_audit_log(
        user=user,
        action='INDENT_CANCELLED',
        entity_type='IndentFile',
        entity_id=indent_id,
        new_value=f"Cancelled: {reason}"
    )
    
    return indent, 'ok'


# ── T-02: Rejection Services ──────────────────────────────────────────────────

def service_reject_indent(indent_id, user, rejection_reason, role):
    """
    T-02: Reject indent with mandatory reason (BR-PS-005)
    Available to all reviewer roles (Dept Admin, Director, HOD)
    """
    if not rejection_reason or rejection_reason.strip() == '':
        raise ValueError("Rejection reason is mandatory")
    
    indent = get_object_or_404(IndentFile, file_info_id=indent_id)
    
    # Guard: Can't reject cancelled or completed
    if indent.status in [IndentStatusChoices.CANCELLED, IndentStatusChoices.COMPLETED]:
        return None, 'invalid_status'
    
    indent.reject(user, rejection_reason)
    
    # T-06: Notify requestor
    requestor = indent.file_info.uploader
    _send_rejection_notification(requestor, indent, rejection_reason, role)
    
    # T-23: Audit log
    _create_audit_log(
        user=user,
        action='INDENT_REJECTED',
        entity_type='IndentFile',
        entity_id=indent_id,
        new_value=f"Rejected by {role}: {rejection_reason}"
    )
    
    return indent, 'ok'


# ── T-03: Cost-Threshold Routing ──────────────────────────────────────────────

def service_determine_routing_by_cost(estimated_total_cost):
    """
    T-03: Determine routing based on cost threshold (BR-PS-004)
    ≤25k → Dept Head
    25k-100k → Dept Head + Registrar
    >100k → Dept Head + Registrar + Director
    """
    routing = ['dept_head']
    
    if estimated_total_cost > COST_THRESHOLD_DEPT_HEAD:
        routing.append('registrar')
    
    if estimated_total_cost > COST_THRESHOLD_REGISTRAR:
        routing.append('director')
    
    return routing


def service_apply_cost_routing(indent, request_user):
    """
    T-03: Apply cost-based routing in create_proposal and forward_indent
    """
    # Calculate total estimated cost
    total_cost = sum(item.estimated_cost or 0 for item in indent.items.all())
    
    # Get required routing
    required_approvals = service_determine_routing_by_cost(total_cost)
    
    # T-08: Check if tender is required
    if total_cost > TENDER_THRESHOLD:
        return 'tender_required', total_cost
    
    return required_approvals, total_cost


# ── T-04: GRN/Delivery Confirmation Services ──────────────────────────────────

@transaction.atomic
def service_create_grn(stock_entry_id, received_by, data):
    """
    T-04: Create Goods Received Note (PSM-UC-002, BR-PS-009, BR-PS-017)
    Required before invoice release
    """
    stock_entry = get_object_or_404(StockEntry, pk=stock_entry_id)
    
    grn = GoodsReceivedNote.objects.create(
        stock_entry=stock_entry,
        indent_file=stock_entry.item_id.indent_file,
        received_by=received_by,
        quantity_received=data.get('quantity_received'),
        quantity_accepted=data.get('quantity_accepted', data.get('quantity_received')),
        quality_check_passed=data.get('quality_check_passed', True),
        remarks=data.get('remarks', ''),
        has_discrepancy=data.get('has_discrepancy', False),
        discrepancy_details=data.get('discrepancy_details', ''),
    )
    
    # T-06: Notify relevant parties
    _send_grn_notification(grn)
    
    return grn


def service_confirm_delivery(grn_id, confirmed_by):
    """
    T-04: Employee confirms receipt for their indent
    """
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id)
    
    grn.confirmed_by = confirmed_by
    grn.confirmed_date = timezone.now()
    
    # Auto-approve invoice release if no discrepancy
    if not grn.has_discrepancy:
        grn.invoice_release_approved = True
    
    grn.save()
    
    return grn


# ── T-05: Product Return Services ─────────────────────────────────────────────

@transaction.atomic
def service_create_product_return(grn_id, initiated_by, data):
    """
    T-05: Create product return (PSM-WF-003, UC-020, BR-PS-018, BR-PS-019)
    """
    grn = get_object_or_404(GoodsReceivedNote, pk=grn_id)
    
    product_return = ProductReturn.objects.create(
        grn=grn,
        stock_entry=grn.stock_entry,
        return_reason=data.get('return_reason'),
        quantity_returned=data.get('quantity_returned'),
        return_initiated_by=initiated_by,
        has_discrepancy=data.get('has_discrepancy', True),
        discrepancy_type=data.get('discrepancy_type', ''),
        discrepancy_description=data.get('discrepancy_description', ''),
    )
    
    # BR-PS-018: Put invoice on hold
    grn.invoice_release_approved = False
    grn.save()
    
    # T-06: Notify purchasing team
    _send_return_notification(product_return)
    
    return product_return


def service_process_return_resolution(return_id, resolved_by, resolution_type, remarks):
    """
    T-05: Process return resolution (refund/replace/reject)
    """
    product_return = get_object_or_404(ProductReturn, pk=return_id)
    
    if resolution_type not in ['REFUND', 'REPLACE', 'REJECT']:
        raise ValueError("Invalid resolution type")
    
    product_return.resolution_type = resolution_type
    product_return.resolved_by = resolved_by
    product_return.resolved_at = timezone.now()
    product_return.resolution_remarks = remarks
    
    # Update status
    if resolution_type == 'REFUND':
        product_return.status = ProductReturn.ReturnStatus.REFUNDED
    elif resolution_type == 'REPLACE':
        product_return.status = ProductReturn.ReturnStatus.REPLACED
    else:
        product_return.status = ProductReturn.ReturnStatus.REJECTED
    
    product_return.save()
    
    # Release invoice hold if rejected
    if resolution_type == 'REJECT':
        product_return.invoice_hold_released = True
        product_return.grn.invoice_release_approved = True
        product_return.grn.save()
        product_return.save()
    
    return product_return


# ── T-08: Tender Management Services ──────────────────────────────────────────

@transaction.atomic
def service_create_tender(indent_id, created_by, data):
    """
    T-08: Create tender for high-value procurement (PSM-UC-022, BR-PS-008)
    """
    indent = get_object_or_404(IndentFile, file_info_id=indent_id)
    
    tender = Tender.objects.create(
        indent_file=indent,
        title=data.get('title'),
        description=data.get('description'),
        estimated_value=data.get('estimated_value'),
        bid_submission_deadline=data.get('bid_submission_deadline'),
        bid_opening_date=data.get('bid_opening_date'),
        created_by=created_by,
    )
    
    return tender


def service_publish_tender(tender_id):
    """T-08: Publish tender to vendors"""
    tender = get_object_or_404(Tender, pk=tender_id)
    
    tender.status = Tender.TenderStatus.PUBLISHED
    tender.publish_date = timezone.now()
    tender.save()
    
    # TODO: Send notifications to approved vendors
    
    return tender


def service_submit_tender_bid(tender_id, vendor_id, data, user):
    """T-08: Vendor submits bid"""
    tender = get_object_or_404(Tender, pk=tender_id)
    vendor = get_object_or_404(Vendor, pk=vendor_id)
    
    # Check deadline
    if timezone.now() > tender.bid_submission_deadline:
        raise ValueError("Bid submission deadline has passed")
    
    # Check vendor approval
    if not vendor.is_approved:
        raise ValueError("Vendor must be approved to submit bids")
    
    bid = TenderBid.objects.create(
        tender=tender,
        vendor=vendor,
        bid_amount=data.get('bid_amount'),
        bid_document=data.get('bid_document'),
        technical_compliance=data.get('technical_compliance', False),
    )
    
    return bid


def service_award_tender(tender_id, winning_bid_id, awarded_by):
    """T-08: Award tender to winning bid"""
    tender = get_object_or_404(Tender, pk=tender_id)
    winning_bid = get_object_or_404(TenderBid, pk=winning_bid_id)
    
    # Mark winning bid
    winning_bid.is_winner = True
    winning_bid.save()
    
    # Update tender
    tender.status = Tender.TenderStatus.AWARDED
    tender.awarded_to = winning_bid.vendor
    tender.awarded_amount = winning_bid.bid_amount
    tender.awarded_at = timezone.now()
    tender.save()
    
    # Update vendor stats
    vendor = winning_bid.vendor
    vendor.total_orders += 1
    vendor.save()
    
    return tender


# ── T-09: Vendor Management Services ──────────────────────────────────────────

def service_create_vendor(created_by, data):
    """
    T-09: Create vendor master (PSM-UC-019, BR-PS-012)
    """
    vendor = Vendor.objects.create(
        vendor_code=data.get('vendor_code'),
        vendor_name=data.get('vendor_name'),
        contact_person=data.get('contact_person', ''),
        email=data.get('email', ''),
        phone=data.get('phone', ''),
        address=data.get('address', ''),
        gst_number=data.get('gst_number', ''),
        pan_number=data.get('pan_number', ''),
        created_by=created_by,
    )
    
    return vendor


def service_validate_vendor(vendor_id):
    """
    T-09: Validate vendor before use in stock entry (BR-PS-012)
    """
    vendor = get_object_or_404(Vendor, pk=vendor_id)
    
    if not vendor.is_approved:
        raise ValueError(f"Vendor {vendor.vendor_code} is not approved")
    
    return vendor


# ── T-10: Automatic Stock Check & Routing ─────────────────────────────────────

def service_check_stock_and_route(indent):
    """
    T-10: Auto stock check on submission (BR-PS-003)
    Routes to internal issue if available, else procurement
    """
    all_items_in_stock = True
    stock_status = []
    
    for item in indent.items.all():
        # Check current stock availability
        available_stock = _get_available_stock_for_item(item.item_name)
        
        stock_status.append({
            'item_name': item.item_name,
            'requested': item.quantity,
            'available': available_stock,
            'in_stock': available_stock >= item.quantity
        })
        
        if available_stock < item.quantity:
            all_items_in_stock = False
    
    # Determine routing
    if all_items_in_stock:
        return 'INTERNAL_ISSUE', stock_status
    else:
        return 'PROCUREMENT', stock_status


def _get_available_stock_for_item(item_name):
    """
    Helper to get available stock (T-13: considering reservations)
    """
    # Get total stock
    total = StockItem.objects.filter(
        nomenclature__icontains=item_name,
        inUse=True
    ).count()
    
    # T-13: Subtract reserved quantity
    reserved = StockReservation.objects.filter(
        stock_item__nomenclature__icontains=item_name,
        is_active=True,
        expires_at__gt=timezone.now()
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    return total - reserved


# ── T-13: Stock Reservation Services ──────────────────────────────────────────

def service_create_stock_reservation(stock_item_id, indent_id, quantity, reserved_by, hours=24):
    """
    T-13: Create stock reservation (BR-PS-013)
    Prevents concurrent holds on same stock
    """
    stock_item = get_object_or_404(StockItem, pk=stock_item_id)
    indent = get_object_or_404(IndentFile, file_info_id=indent_id)
    
    # Check available quantity
    available = _get_available_stock_for_item(stock_item.nomenclature)
    if available < quantity:
        raise ValueError(f"Insufficient stock. Available: {available}, Requested: {quantity}")
    
    reservation = StockReservation.objects.create(
        stock_item=stock_item,
        indent_file=indent,
        quantity=quantity,
        reserved_by=reserved_by,
        expires_at=timezone.now() + timedelta(hours=hours),
    )
    
    return reservation


def service_release_reservation(reservation_id):
    """T-13: Release/cancel stock reservation"""
    reservation = get_object_or_404(StockReservation, pk=reservation_id)
    reservation.is_active = False
    reservation.save()
    return reservation


# ── T-15: Duplicate Detection ─────────────────────────────────────────────────

def service_check_duplicate_indent(user, items, department):
    """
    T-15: Check for duplicate indents (BR-PS-015)
    Same item + dept + active status within configured time window
    """
    # Get time window
    cutoff_time = timezone.now() - timedelta(hours=DUPLICATE_DETECTION_WINDOW_HOURS)
    
    duplicates = []
    
    for item_data in items:
        # Find matching indents
        matching_indents = IndentFile.objects.filter(
            file_info__uploader=user,
            status=IndentStatusChoices.ACTIVE,
            file_info__upload_date__gte=cutoff_time,
            items__item_name__iexact=item_data.get('item_name'),
        ).distinct()
        
        if matching_indents.exists():
            duplicates.append({
                'item_name': item_data.get('item_name'),
                'existing_indents': [indent.file_info_id for indent in matching_indents]
            })
    
    if duplicates:
        return True, duplicates
    
    return False, []


# ── T-14: SLA Tracking (to be called by Celery periodic task) ────────────────

def service_check_sla_deadlines():
    """
    T-14: Check SLA deadlines and escalate (BR-PS-014)
    Should be run periodically by Celery
    """
    now = timezone.now()
    overdue_indents = IndentFile.objects.filter(
        status=IndentStatusChoices.ACTIVE,
        sla_deadline__lt=now,
        escalated=False
    )
    
    for indent in overdue_indents:
        _escalate_indent(indent)


def _escalate_indent(indent):
    """T-14: Escalate overdue indent"""
    indent.escalated = True
    indent.escalation_count += 1
    
    # Extend deadline for next escalation
    indent.sla_deadline = timezone.now() + timedelta(hours=24)
    indent.save()
    
    # TODO: Send escalation notifications
    

# ── T-23: Audit Logging ───────────────────────────────────────────────────────

def _create_audit_log(user, action, entity_type, entity_id, old_value='', new_value='', request=None):
    """
    T-23: Create audit log entry (UC-014)
    """
    ip_address = None
    user_agent = ''
    
    if request:
        ip_address = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    AuditLog.objects.create(
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _get_client_ip(request):
    """Helper to get client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ── Notification Helpers ──────────────────────────────────────────────────────

def _send_rejection_notification(user, indent, reason, role):
    """T-06: Send notification on rejection"""
    # TODO: Implement notification
    pass


def _send_grn_notification(grn):
    """T-06: Send notification on GRN creation"""
    # TODO: Implement notification
    pass


def _send_return_notification(product_return):
    """T-06: Send notification on return initiation"""
    # TODO: Implement notification
    pass
