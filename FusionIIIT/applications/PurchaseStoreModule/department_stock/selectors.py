from __future__ import annotations

from django.shortcuts import get_object_or_404

from psmodule.department_stock.models import Stock, TransferLog, TransferRequest


def stock_queryset_for_department(department: str):
    return Stock.objects.filter(department=department)


def stock_queryset_excluding_department(department: str):
    return Stock.objects.exclude(department=department)


def transfer_requests_for_listing(user, depadmin_role: str | None, ps_admin_role: str | None):
    if ps_admin_role:
        qs = TransferRequest.objects.filter(status=TransferRequest.Status.APPROVED)
    else:
        qs = TransferRequest.objects.filter(requested_by=user)
        qs = qs | TransferRequest.objects.filter(requested_from=depadmin_role)
    return qs.select_related("stock", "requested_by").order_by("-created_at").distinct()


def get_stock_by_pk(pk: int) -> Stock:
    return Stock.objects.get(pk=pk)


def get_transfer_request_or_404(pk: int, *, select_related=None) -> TransferRequest:
    qs = TransferRequest.objects.all()
    if select_related:
        qs = qs.select_related(*select_related)
    return get_object_or_404(qs, pk=pk)


def create_transfer_request_pending(
    *,
    stock: Stock,
    requested_by,
    requested_from: str,
    requested_quantity: int,
) -> TransferRequest:
    return TransferRequest.objects.create(
        stock=stock,
        requested_by=requested_by,
        requested_from=requested_from,
        requested_quantity=requested_quantity,
        status=TransferRequest.Status.PENDING,
    )


def save_stock_quantity(stock: Stock, quantity: int) -> None:
    stock.quantity = quantity
    stock.save(update_fields=["quantity"])


def increment_destination_stock(
    stock_name: str, department: str, quantity: int
) -> None:
    destination_stock, created = Stock.objects.get_or_create(
        stock_name=stock_name,
        department=department,
        defaults={"quantity": quantity},
    )
    if not created:
        destination_stock.quantity += quantity
        destination_stock.save(update_fields=["quantity"])


def mark_transfer_request_approved(transfer_request: TransferRequest) -> None:
    transfer_request.status = TransferRequest.Status.APPROVED
    transfer_request.save(update_fields=["status"])


def mark_transfer_request_rejected(transfer_request: TransferRequest) -> None:
    transfer_request.status = TransferRequest.Status.REJECTED
    transfer_request.save(update_fields=["status"])


def create_transfer_log(
    *,
    stock: Stock,
    from_department: str,
    to_department: str,
    approved_by,
) -> TransferLog:
    return TransferLog.objects.create(
        stock=stock,
        from_department=from_department,
        to_department=to_department,
        approved_by=approved_by,
    )


def apply_received_quantities_to_department_stock(
    department_code: str | None,
    item_quantities: dict[int, int],
) -> None:
    """
    When central-store stock entry receives goods for an indent, mirror quantities
    into department_stock.Stock for that indent's department (same keys as transfer
    flow: department ``dep_{code.lower()}``, stock_name = StoreItem.name).
    """
    if not department_code or not item_quantities:
        return

    from psmodule.models import StoreItem

    code = str(department_code).strip().lower()
    if not code:
        return

    dept_key = f"dep_{code}"
    quantities = {int(i): int(q) for i, q in item_quantities.items() if int(q) != 0}
    if not quantities:
        return

    item_ids = list(quantities.keys())
    id_to_name = dict(StoreItem.objects.filter(pk__in=item_ids).values_list("id", "name"))

    for item_id, qty in quantities.items():
        raw = id_to_name.get(item_id) or f"Item {item_id}"
        stock_name = str(raw).strip()[:255] or f"Item {item_id}"
        increment_destination_stock(
            stock_name=stock_name,
            department=dept_key,
            quantity=qty,
        )
