from __future__ import annotations

from django.db import transaction
from django.http import HttpResponseForbidden

from rest_framework import status

from psmodule.department_stock import selectors
from psmodule.department_stock.models import TransferRequest
from psmodule.department_stock.permissions import (
    get_user_depadmin_role,
    get_user_ps_admin_role,
    require_depadmin_role,
)


def department_stock_queryset_for_request(request):
    """Returns a Stock queryset for the depadmin's department, or HttpResponseForbidden."""
    department = require_depadmin_role(request)
    if isinstance(department, HttpResponseForbidden):
        return department
    return selectors.stock_queryset_for_department(department)


def available_stock_queryset_for_request(request):
    """Returns a Stock queryset excluding the depadmin's department, or HttpResponseForbidden."""
    department = require_depadmin_role(request)
    if isinstance(department, HttpResponseForbidden):
        return department
    return selectors.stock_queryset_excluding_department(department)


def transfer_request_list_queryset(request):
    """
    Returns a queryset of transfer requests for GET /request/ or None if forbidden.
    """
    depadmin_role = get_user_depadmin_role(request.user)
    ps_admin_role = get_user_ps_admin_role(request.user)

    if not depadmin_role and not ps_admin_role:
        return None

    return selectors.transfer_requests_for_listing(
        request.user, depadmin_role, ps_admin_role
    )


def create_transfer_request_record(
    request, stock_id: int, requested_from: str, requested_quantity: int
):
    """
    Creates a pending transfer request after permission check.
    Returns HttpResponseForbidden or the created TransferRequest instance.
    """
    department = require_depadmin_role(request)
    if isinstance(department, HttpResponseForbidden):
        return department

    stock = selectors.get_stock_by_pk(stock_id)
    return selectors.create_transfer_request_pending(
        stock=stock,
        requested_by=request.user,
        requested_from=requested_from,
        requested_quantity=requested_quantity,
    )


def approve_transfer_request(request, pk: int):
    """
    Returns HttpResponseForbidden, or (error_payload, http_status), or TransferRequest on success.
    """
    department = require_depadmin_role(request)
    if isinstance(department, HttpResponseForbidden):
        return department

    transfer_request = selectors.get_transfer_request_or_404(
        pk, select_related=("stock", "requested_by")
    )

    if transfer_request.status != TransferRequest.Status.PENDING:
        return (
            {"detail": "Only pending requests can be approved."},
            status.HTTP_400_BAD_REQUEST,
        )

    if transfer_request.stock.department != department:
        return (
            {"detail": "Access Denied"},
            status.HTTP_403_FORBIDDEN,
        )

    requested_by_role = get_user_depadmin_role(transfer_request.requested_by)
    if not isinstance(requested_by_role, str) or not requested_by_role.startswith(
        "depadmin_"
    ):
        return (
            {"detail": "Invalid requester role."},
            status.HTTP_400_BAD_REQUEST,
        )

    destination_department = requested_by_role.replace("depadmin_", "dep_")
    requested_quantity = transfer_request.requested_quantity
    source_stock = transfer_request.stock

    if requested_quantity > source_stock.quantity:
        return (
            {"detail": "Requested quantity exceeds available stock."},
            status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        selectors.save_stock_quantity(
            source_stock, source_stock.quantity - requested_quantity
        )

        selectors.increment_destination_stock(
            stock_name=source_stock.stock_name,
            department=destination_department,
            quantity=requested_quantity,
        )

        selectors.mark_transfer_request_approved(transfer_request)

        selectors.create_transfer_log(
            stock=source_stock,
            from_department=department,
            to_department=destination_department,
            approved_by=request.user,
        )

    return transfer_request


def reject_transfer_request(request, pk: int):
    """Returns HttpResponseForbidden, or (error_payload, http_status), or TransferRequest on success."""
    department = require_depadmin_role(request)
    if isinstance(department, HttpResponseForbidden):
        return department

    transfer_request = selectors.get_transfer_request_or_404(
        pk, select_related=("stock",)
    )

    if transfer_request.status != TransferRequest.Status.PENDING:
        return (
            {"detail": "Only pending requests can be rejected."},
            status.HTTP_400_BAD_REQUEST,
        )

    if transfer_request.stock.department != department:
        return (
            {"detail": "Access Denied"},
            status.HTTP_403_FORBIDDEN,
        )

    selectors.mark_transfer_request_rejected(transfer_request)
    return transfer_request
