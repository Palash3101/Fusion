"""
API Views - Assignment 7 Additions

New REST API endpoints for Assignment 7 functionality.
Improvements applied:
  - Metric 3: @transaction.atomic on all write operations
  - Metric 4: RBAC via permissions.py role decorators
  - Metric 5: Structured logging, consistent error shape
  - Metric 8: select_related/prefetch_related on all querysets
  - Metric 10: Uniform error responses with codes
"""

import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction

from applications.ps1.models import (
    IndentFile, Vendor, GoodsReceivedNote, ProductReturn,
    Tender, TenderBid, StockReservation, AuditLog
)
from applications.ps1.api.serializers import (
    VendorSerializer, GoodsReceivedNoteSerializer,
    ProductReturnSerializer, TenderSerializer, TenderBidSerializer,
    StockReservationSerializer, AuditLogSerializer, IndentFileSerializer
)
from applications.ps1.api.permissions import (
    require_roles, has_any_role,
    ROLE_PS_ADMIN, ROLE_DEPT_ADMIN, ROLE_DEPT_HEAD,
    ROLE_DIRECTOR, ROLE_REGISTRAR, ROLE_ACCOUNTS,
    APPROVER_ROLES, PROCUREMENT_ROLES, ADMIN_ROLES
)
from applications.ps1.services_assignment7_additions import (
    service_soft_cancel_indent, service_reject_indent,
    service_create_grn, service_confirm_delivery,
    service_create_product_return, service_process_return_resolution,
    service_create_tender, service_publish_tender,
    service_submit_tender_bid, service_award_tender,
    service_create_vendor, service_validate_vendor,
    service_create_stock_reservation, service_release_reservation,
    service_check_duplicate_indent
)

logger = logging.getLogger('ps1.views')


def _error(msg, code=None, http_status=status.HTTP_400_BAD_REQUEST):
    """Consistent error response shape."""
    body = {'error': msg}
    if code:
        body['code'] = code
    return Response(body, status=http_status)


# ── T-01: Soft Cancel ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_indent(request, indent_id):
    """
    T-01: Soft-cancel indent with reason (BR-PS-007).
    Allowed: indent owner or APPROVER_ROLES.
    POST /api/indents/{indent_id}/cancel/
    Body: {"reason": "Duplicate request"}
    """
    reason = request.data.get('reason', '').strip()
    if not reason:
        return _error('Cancellation reason is required', code='REASON_REQUIRED')

    # RBAC: allow owner or approvers
    indent = get_object_or_404(
        IndentFile.objects.select_related('file_info__uploader__user'),
        file_info_id=indent_id
    )
    is_owner = indent.file_info.uploader.user == request.user
    is_approver = has_any_role(request.user, APPROVER_ROLES | PROCUREMENT_ROLES)
    if not (is_owner or is_approver):
        return _error(
            'You are not authorised to cancel this indent.',
            code='FORBIDDEN',
            http_status=status.HTTP_403_FORBIDDEN
        )

    try:
        with transaction.atomic():
            indent, result = service_soft_cancel_indent(indent_id, request.user, reason)
    except Exception as exc:
        logger.exception('cancel_indent failed: indent=%s user=%s', indent_id, request.user)
        return _error(str(exc), code='CANCEL_ERROR', http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if result == 'already_cancelled':
        return _error('Indent is already cancelled', code='ALREADY_CANCELLED')
    if result == 'cannot_cancel_completed':
        return _error('Cannot cancel a completed indent', code='INVALID_STATE')

    logger.info('cancel_indent: indent=%s cancelled_by=%s', indent_id, request.user.username)
    return Response(IndentFileSerializer(indent).data, status=status.HTTP_200_OK)


# ── T-02: Rejection ───────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_indent(request, indent_id):
    """
    T-02: Reject indent with mandatory reason (BR-PS-005, BR-PS-010).
    Allowed: APPROVER_ROLES only.
    POST /api/indents/{indent_id}/reject/
    Body: {"rejection_reason": "...", "role": "deptadmin_cse"}
    """
    if not has_any_role(request.user, APPROVER_ROLES | PROCUREMENT_ROLES):
        return _error(
            'Only approvers may reject indents.',
            code='FORBIDDEN',
            http_status=status.HTTP_403_FORBIDDEN
        )

    rejection_reason = request.data.get('rejection_reason', '').strip()
    role = request.data.get('role', '').strip()

    if not rejection_reason:
        return _error('rejection_reason is required', code='REASON_REQUIRED')
    if not role:
        return _error('role is required', code='ROLE_REQUIRED')

    try:
        with transaction.atomic():
            indent, result = service_reject_indent(
                indent_id, request.user, rejection_reason, role
            )
    except ValueError as exc:
        return _error(str(exc), code='VALIDATION_ERROR')
    except Exception as exc:
        logger.exception('reject_indent failed: indent=%s', indent_id)
        return _error('Internal error during rejection', http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if result == 'invalid_status':
        return _error('Cannot reject indent in current status', code='INVALID_STATE')

    logger.info('reject_indent: indent=%s rejected_by=%s', indent_id, request.user.username)
    return Response(IndentFileSerializer(indent).data, status=status.HTTP_200_OK)


# ── T-04: GRN ─────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_grn(request):
    """
    T-04: Create GRN (BR-PS-009, BR-PS-017).
    Allowed: PS_Admin, Dept_Admin.
    POST /api/grn/create/
    """
    if not has_any_role(request.user, PROCUREMENT_ROLES):
        return _error('Only PS Admin or Dept Admin may create GRNs', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    stock_entry_id = request.data.get('stock_entry_id')
    if not stock_entry_id:
        return _error('stock_entry_id is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            grn = service_create_grn(stock_entry_id, request.user, request.data)
    except Exception as exc:
        logger.exception('create_grn failed: stock_entry=%s', stock_entry_id)
        return _error(str(exc), code='GRN_ERROR')

    logger.info('create_grn: grn=%s by=%s', grn.grn_number, request.user.username)
    return Response(GoodsReceivedNoteSerializer(grn).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_delivery(request, grn_id):
    """
    T-04: Confirm GRN delivery (BR-PS-009).
    Allowed: any authenticated user (requestor confirms receipt).
    POST /api/grn/{grn_id}/confirm/
    """
    try:
        with transaction.atomic():
            grn = service_confirm_delivery(grn_id, request.user)
    except Exception as exc:
        logger.exception('confirm_delivery failed: grn=%s', grn_id)
        return _error(str(exc), code='CONFIRM_ERROR')

    logger.info('confirm_delivery: grn=%s confirmed_by=%s', grn_id, request.user.username)
    return Response(GoodsReceivedNoteSerializer(grn).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_grns(request):
    """
    T-04: List GRNs (with select_related for N+1 prevention).
    GET /api/grn/
    """
    grns = (
        GoodsReceivedNote.objects
        .select_related('indent_file', 'stock_entry', 'received_by', 'confirmed_by')
        .order_by('-received_date')
    )
    return Response(GoodsReceivedNoteSerializer(grns, many=True).data)


# ── T-05: Product Returns ─────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_return(request):
    """
    T-05: Create product return (BR-PS-018, BR-PS-019, WF-003).
    Allowed: PS_Admin, Dept_Admin.
    POST /api/returns/create/
    """
    if not has_any_role(request.user, PROCUREMENT_ROLES):
        return _error('Only PS Admin or Dept Admin may initiate returns', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    grn_id = request.data.get('grn_id')
    if not grn_id:
        return _error('grn_id is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            product_return = service_create_product_return(
                grn_id, request.user, request.data
            )
    except Exception as exc:
        logger.exception('create_return failed: grn=%s', grn_id)
        return _error(str(exc), code='RETURN_ERROR')

    logger.info('create_return: return=%s by=%s', product_return.return_number, request.user.username)
    return Response(ProductReturnSerializer(product_return).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_return(request, return_id):
    """
    T-05: Process return resolution (BR-PS-019).
    Allowed: PS_Admin only.
    POST /api/returns/{return_id}/process/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN}):
        return _error('Only PS Admin may process return resolutions', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    resolution_type = request.data.get('resolution_type', '').strip()
    remarks = request.data.get('remarks', '')

    valid_types = {'REFUND', 'REPLACE', 'REJECT'}
    if not resolution_type or resolution_type not in valid_types:
        return _error(
            f'resolution_type must be one of: {", ".join(valid_types)}',
            code='INVALID_RESOLUTION'
        )

    try:
        with transaction.atomic():
            product_return = service_process_return_resolution(
                return_id, request.user, resolution_type, remarks
            )
    except ValueError as exc:
        return _error(str(exc), code='VALIDATION_ERROR')
    except Exception as exc:
        logger.exception('process_return failed: return=%s', return_id)
        return _error('Internal error processing return', http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info('process_return: return=%s resolution=%s by=%s', return_id, resolution_type, request.user.username)
    return Response(ProductReturnSerializer(product_return).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_returns(request):
    """
    T-05: List product returns.
    GET /api/returns/
    """
    returns = (
        ProductReturn.objects
        .select_related('grn', 'stock_entry', 'return_initiated_by', 'resolved_by')
        .order_by('-return_date')
    )
    return Response(ProductReturnSerializer(returns, many=True).data)


# ── T-08: Tender Management ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_tender(request):
    """
    T-08: Create tender (BR-PS-008, UC-022).
    Allowed: PS_Admin.
    POST /api/tenders/create/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN}):
        return _error('Only PS Admin may create tenders', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    indent_id = request.data.get('indent_id')
    if not indent_id:
        return _error('indent_id is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            tender = service_create_tender(indent_id, request.user, request.data)
    except Exception as exc:
        logger.exception('create_tender failed: indent=%s', indent_id)
        return _error(str(exc), code='TENDER_ERROR')

    logger.info('create_tender: tender=%s by=%s', tender.tender_number, request.user.username)
    return Response(TenderSerializer(tender).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publish_tender(request, tender_id):
    """
    T-08: Publish tender.
    Allowed: PS_Admin.
    POST /api/tenders/{tender_id}/publish/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN}):
        return _error('Only PS Admin may publish tenders', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    try:
        with transaction.atomic():
            tender = service_publish_tender(tender_id)
    except Exception as exc:
        logger.exception('publish_tender failed: tender=%s', tender_id)
        return _error(str(exc), code='PUBLISH_ERROR')

    logger.info('publish_tender: tender=%s by=%s', tender_id, request.user.username)
    return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_bid(request, tender_id):
    """
    T-08: Submit tender bid.
    Allowed: any authenticated user (vendor representative).
    POST /api/tenders/{tender_id}/bid/
    """
    vendor_id = request.data.get('vendor_id')
    if not vendor_id:
        return _error('vendor_id is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            bid = service_submit_tender_bid(
                tender_id, vendor_id, request.data, request.user
            )
    except ValueError as exc:
        return _error(str(exc), code='BID_ERROR')
    except Exception as exc:
        logger.exception('submit_bid failed: tender=%s', tender_id)
        return _error('Internal error submitting bid', http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(TenderBidSerializer(bid).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def award_tender(request, tender_id):
    """
    T-08: Award tender to winning bid.
    Allowed: PS_Admin, Director.
    POST /api/tenders/{tender_id}/award/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN, ROLE_DIRECTOR}):
        return _error('Only PS Admin or Director may award tenders', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    winning_bid_id = request.data.get('winning_bid_id')
    if not winning_bid_id:
        return _error('winning_bid_id is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            tender = service_award_tender(tender_id, winning_bid_id, request.user)
    except Exception as exc:
        logger.exception('award_tender failed: tender=%s', tender_id)
        return _error(str(exc), code='AWARD_ERROR')

    logger.info('award_tender: tender=%s by=%s', tender_id, request.user.username)
    return Response(TenderSerializer(tender).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_tenders(request):
    """
    T-08: List tenders with prefetched bids (N+1 safe).
    GET /api/tenders/
    """
    tenders = (
        Tender.objects
        .select_related('indent_file', 'awarded_to', 'created_by')
        .prefetch_related('bids__vendor')
        .order_by('-created_at')
    )
    return Response(TenderSerializer(tenders, many=True).data)


# ── T-09: Vendor Management ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_vendor(request):
    """
    T-09: Create vendor (BR-PS-012, UC-019).
    Allowed: PS_Admin.
    POST /api/vendors/create/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN}):
        return _error('Only PS Admin may create vendors', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    try:
        with transaction.atomic():
            vendor = service_create_vendor(request.user, request.data)
    except Exception as exc:
        logger.exception('create_vendor failed: user=%s', request.user.username)
        return _error(str(exc), code='VENDOR_ERROR')

    logger.info('create_vendor: vendor=%s by=%s', vendor.vendor_code, request.user.username)
    return Response(VendorSerializer(vendor).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_vendors(request):
    """T-09: List all vendors. Allowed: authenticated users."""
    vendors = Vendor.objects.all().order_by('vendor_name')
    # Optional search filter
    q = request.GET.get('q', '').strip()
    if q:
        vendors = vendors.filter(vendor_name__icontains=q)
    return Response(VendorSerializer(vendors, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_vendor(request, vendor_id):
    """T-09: Get single vendor details."""
    vendor = get_object_or_404(Vendor, pk=vendor_id)
    return Response(VendorSerializer(vendor).data)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_vendor(request, vendor_id):
    """
    T-09: Update vendor.
    Allowed: PS_Admin.
    PUT/PATCH /api/vendors/{vendor_id}/update/
    """
    if not has_any_role(request.user, {ROLE_PS_ADMIN}):
        return _error('Only PS Admin may update vendors', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    vendor = get_object_or_404(Vendor, pk=vendor_id)
    serializer = VendorSerializer(vendor, data=request.data, partial=True)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            serializer.save()
    except Exception as exc:
        logger.exception('update_vendor failed: vendor=%s', vendor_id)
        return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info('update_vendor: vendor=%s by=%s', vendor_id, request.user.username)
    return Response(serializer.data)


# ── T-13: Stock Reservation ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_reservation(request):
    """
    T-13: Reserve stock to prevent double allocation (BR-PS-013).
    Allowed: Dept_Admin, PS_Admin.
    POST /api/reservations/create/
    """
    if not has_any_role(request.user, PROCUREMENT_ROLES):
        return _error('Only PS Admin or Dept Admin may create reservations', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    required = ['stock_item_id', 'indent_id', 'quantity']
    for field in required:
        if not request.data.get(field):
            return _error(f'{field} is required', code='FIELD_REQUIRED')

    try:
        with transaction.atomic():
            reservation = service_create_stock_reservation(
                request.data['stock_item_id'],
                request.data['indent_id'],
                request.data['quantity'],
                request.user,
                request.data.get('hours', 24)
            )
    except ValueError as exc:
        return _error(str(exc), code='RESERVATION_ERROR')
    except Exception as exc:
        logger.exception('create_reservation failed')
        return _error('Internal error creating reservation', http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(StockReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def release_reservation(request, reservation_id):
    """
    T-13: Release stock reservation.
    Allowed: Dept_Admin, PS_Admin.
    POST /api/reservations/{reservation_id}/release/
    """
    if not has_any_role(request.user, PROCUREMENT_ROLES):
        return _error('Only PS Admin or Dept Admin may release reservations', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    try:
        with transaction.atomic():
            reservation = service_release_reservation(reservation_id)
    except Exception as exc:
        logger.exception('release_reservation failed: id=%s', reservation_id)
        return _error(str(exc), code='RELEASE_ERROR')

    return Response(StockReservationSerializer(reservation).data, status=status.HTTP_200_OK)


# ── T-15: Duplicate Check ─────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_duplicates(request):
    """
    T-15: Detect potential duplicate indents (BR-PS-015).
    POST /api/indents/check-duplicates/
    Body: {"items": [...], "department": "CSE"}
    """
    items = request.data.get('items', [])
    department = request.data.get('department', '').strip()

    if not items:
        return _error('items list is required', code='FIELD_REQUIRED')

    has_duplicates, duplicates = service_check_duplicate_indent(
        request.user, items, department
    )

    return Response({
        'has_duplicates': has_duplicates,
        'duplicates': duplicates,
        'message': (
            f'Found {len(duplicates)} potential duplicate indent(s). Review before submitting.'
            if has_duplicates else 'No duplicates detected.'
        )
    })


# ── T-23: Audit Logs ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_audit_logs(request):
    """
    T-23: List audit logs (UC-014).
    Allowed: Auditor, PS_Admin, Accounts_Admin.
    GET /api/audit-logs/?entity_type=IndentFile&entity_id=5
    """
    from applications.ps1.api.permissions import ROLE_ACCOUNTS, ROLE_AUDITOR
    if not has_any_role(request.user, {ROLE_PS_ADMIN, ROLE_ACCOUNTS, ROLE_AUDITOR}):
        return _error('Only auditors or admins may view audit logs', code='FORBIDDEN',
                      http_status=status.HTTP_403_FORBIDDEN)

    logs = AuditLog.objects.select_related('user').order_by('-timestamp')

    entity_type = request.GET.get('entity_type')
    entity_id = request.GET.get('entity_id')
    user_id = request.GET.get('user')
    limit = min(int(request.GET.get('limit', 100)), 500)

    if entity_type:
        logs = logs.filter(entity_type=entity_type)
    if entity_id:
        logs = logs.filter(entity_id=entity_id)
    if user_id:
        logs = logs.filter(user_id=user_id)

    logs = logs[:limit]
    return Response(AuditLogSerializer(logs, many=True).data)
