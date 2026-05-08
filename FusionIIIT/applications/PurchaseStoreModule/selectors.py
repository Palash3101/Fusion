from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotAuthenticated, PermissionDenied, ValidationError

from psmodule.accounts.models import DepartmentInfo, ExtraInfo, HoldsDesignation
from psmodule.models import (
    ActingRole,
    CurrentStock,
    Indent,
    IndentAudit,
    IndentItem,
    StockAllocation,
    StockAllocationItem,
    StockCheckStatus,
    StockEntry,
    StockEntryItem,
    StoreItem,
)
from psmodule.api.serializers import IndentSerializer


def get_extrainfo_for_user(user) -> ExtraInfo:
    if not getattr(user, "is_authenticated", False):
        raise NotAuthenticated()
    try:
        return ExtraInfo.objects.select_related("department").get(user=user)
    except ExtraInfo.DoesNotExist as e:  # type: ignore[attr-defined]
        raise PermissionDenied("User missing ExtraInfo") from e


def has_designation(extrainfo: ExtraInfo, name_contains: str) -> bool:
    return HoldsDesignation.objects.filter(
        is_active=True,
        designation__name__icontains=name_contains,
        working=extrainfo,
    ).exists()


def is_user_hod(extrainfo: ExtraInfo) -> bool:
    # Treat common variants as department head
    return (
        HoldsDesignation.objects.filter(is_active=True, working=extrainfo)
        .filter(designation__name__icontains="hod")
        .exists()
        or HoldsDesignation.objects.filter(is_active=True, working=extrainfo)
        .filter(designation__name__icontains="dept head")
        .exists()
        or HoldsDesignation.objects.filter(is_active=True, working=extrainfo)
        .filter(designation__name__icontains="head of department")
        .exists()
    )


def validate_store_item_ids(item_ids: Sequence[int]) -> None:
    item_ids_set = set(item_ids)
    if not item_ids_set:
        return

    existing = set(
        StoreItem.objects.filter(id__in=item_ids_set).values_list("id", flat=True)
    )
    missing = sorted([i for i in item_ids_set if i not in existing])
    if missing:
        raise ValidationError({"item_id": f"Unknown item_ids: {missing}"})


def get_department_hod(department: DepartmentInfo) -> Optional[ExtraInfo]:
    hold = (
        HoldsDesignation.objects.select_related(
            "working", "designation", "working__department"
        )
        .filter(
            is_active=True,
            designation__name__iregex=r"(hod|dept head|head of department)",
            working__department=department,
        )
        .first()
    )
    return hold.working if hold else None


def get_department_depadmin(department: DepartmentInfo) -> Optional[ExtraInfo]:
    hold = (
        HoldsDesignation.objects.select_related(
            "working", "designation", "working__department"
        )
        .filter(
            is_active=True,
            designation__name__icontains="depadmin",
            working__department=department,
        )
        .first()
    )
    return hold.working if hold else None


def get_first_holder_by_designation(name_contains: str) -> Optional[ExtraInfo]:
    hold = (
        HoldsDesignation.objects.select_related(
            "working", "designation", "working__department"
        )
        .filter(is_active=True, designation__name__icontains=name_contains)
        .first()
    )
    return hold.working if hold else None


def get_registrar_or_director() -> Optional[ExtraInfo]:
    return get_first_holder_by_designation(
        "registrar"
    ) or get_first_holder_by_designation("director")


def get_accounts_admin() -> Optional[ExtraInfo]:
    return get_first_holder_by_designation("accounts")


def get_department_by_code(code: str) -> DepartmentInfo:
    dept = DepartmentInfo.objects.filter(code__iexact=code).first()
    if not dept:
        raise ValidationError(
            {"forward_to_department_code": "Unknown department code."}
        )
    return dept


def check_stock_availability_for_indent_id(indent_id: int) -> bool:
    """
    Read-only stock check for INTERNAL procurement eligibility.

    Returns True if, for every indent line:
      - central CurrentStock >= required quantity, OR
      - department's own Stock has the item with sufficient quantity
    
    This allows indents to be marked as INTERNAL if stock is available either
    centrally or within the requesting department.
    """
    indent = Indent.objects.filter(id=indent_id).first()
    if not indent:
        return False
    
    lines = list(
        IndentItem.objects.filter(indent_id=indent_id, item_id__isnull=False).values(
            "item_id", "quantity"
        )
    )
    if not lines:
        return False

    item_ids = [l["item_id"] for l in lines if l["item_id"] is not None]
    
    # Check central stock
    central_stock_map: Dict[int, int] = dict(
        CurrentStock.objects.filter(item_id__in=item_ids).values_list(
            "item_id", "quantity"
        )
    )

    # Check department stock (if indent has a department)
    dept_stock_map: Dict[str, int] = {}
    if indent.department:
        from psmodule.department_stock.models import Stock as DepartmentStock
        
        dept_code = getattr(indent.department, "code", None)
        dept_lookup_values = []
        if dept_code:
            dept_lookup_values.append(f"dep_{dept_code.lower()}")
            dept_lookup_values.append(dept_code.lower())
        dept_lookup_values.append(f"dep_{indent.department.id}")
        dept_lookup_values.append(str(indent.department.id))
        
        dept_stock_qs = DepartmentStock.objects.filter(
            department__in=[v for v in dept_lookup_values if v]
        ).values_list("stock_name", "quantity")
        dept_stock_map = {
            str(stock_name).strip().lower(): qty for stock_name, qty in dept_stock_qs
        }

    # Resolve item IDs to item names for department stock lookup
    from psmodule.models import StoreItem
    item_name_map = dict(
        StoreItem.objects.filter(id__in=item_ids).values_list("id", "name")
    )

    for l in lines:
        item_id = l["item_id"]
        required = l["quantity"]
        
        # Check central stock first
        central_avail = central_stock_map.get(item_id, 0)
        if central_avail >= required:
            continue
        
        # Check department stock with case-insensitive matching
        item_name = item_name_map.get(item_id, "")
        dept_avail = 0
        if item_name:
            # Try exact match first
            dept_avail = dept_stock_map.get(item_name, 0)
            
            # If not found, try case-insensitive match
            if dept_avail == 0:
                item_name_lower = item_name.lower()
                for stock_name, qty in dept_stock_map.items():
                    if stock_name.lower() == item_name_lower:
                        dept_avail = qty
                        break
        
        if dept_avail >= required:
            continue
        
        # Item not available in either location
        return False
    
    return True


def get_indent_data(indent_id: int, *, request=None) -> dict:
    indent = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .get(id=indent_id)
    )
    return IndentSerializer(indent, context={"request": request}).data


def indent_visible_to_actor(indent: Indent, actor) -> bool:
    if actor.role == ActingRole.EMPLOYEE:
        return indent.indenter_id == actor.extrainfo.id
    if actor.role == ActingRole.PS_ADMIN:
        return indent.status in (
            Indent.Status.EXTERNAL_PROCUREMENT,
            Indent.Status.APPROVED,
            Indent.Status.BIDDING,
            Indent.Status.PURCHASED,
            Indent.Status.STOCK_ENTRY,
            Indent.Status.STOCKED,
        )
    if actor.role in (
        ActingRole.DEPADMIN,
        ActingRole.HOD,
        ActingRole.REGISTRAR,
        ActingRole.DIRECTOR,
    ):
        return indent.current_approver_id == actor.extrainfo.id
    return False


def get_indent_detail_data(indent_id: int, actor, *, request=None) -> dict:
    indent = get_object_or_404(
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        ).prefetch_related("items__item", "documents"),
        pk=indent_id,
    )
    if not indent_visible_to_actor(indent, actor):
        raise PermissionDenied("Cannot view this indent.")
    return get_indent_data(indent_id, request=request)


def get_indent_for_hod_action(indent_id: int, actor) -> Indent:
    if actor.role not in (
        ActingRole.DEPADMIN,
        ActingRole.HOD,
        ActingRole.REGISTRAR,
        ActingRole.DIRECTOR,
    ):
        raise PermissionDenied("Not allowed to perform approval actions.")

    indent = (
        Indent.objects.select_related("indenter", "department", "current_approver")
        .prefetch_related("items__item")
        .filter(id=indent_id, current_approver=actor.extrainfo)
        .first()
    )
    if not indent:
        raise PermissionDenied("You are not the current approver for this indent.")
    return indent


def get_indent_for_stock_check(indent_id: int, actor) -> Indent:
    if actor.role != ActingRole.DEPADMIN:
        raise PermissionDenied("Only DepAdmin can check stock.")

    indent = (
        Indent.objects.select_related("indenter", "department", "current_approver")
        .prefetch_related("items__item")
        .filter(id=indent_id, current_approver=actor.extrainfo)
        .first()
    )
    if not indent:
        raise PermissionDenied("Cannot check this indent.")

    if indent.department_id != actor.extrainfo.department_id:
        raise PermissionDenied("Cannot check other department's indent.")
    return indent


def get_stock_breakdown_data(indent_id: int, actor) -> dict:
    if actor.role not in (ActingRole.DEPADMIN, ActingRole.HOD):
        raise PermissionDenied("Only DepAdmin/HOD can view stock breakdown.")

    indent = (
        Indent.objects.select_related("department")
        .filter(id=indent_id, current_approver=actor.extrainfo)
        .first()
    )
    if not indent:
        raise PermissionDenied("Cannot view this indent.")

    if indent.department_id != actor.extrainfo.department_id:
        raise PermissionDenied("Cannot view other department's indent.")

    lines = list(
        IndentItem.objects.filter(indent_id=indent_id, item_id__isnull=False)
        .select_related("item")
        .values("item_id", "quantity", "item__name")
    )
    item_ids = [l["item_id"] for l in lines if l["item_id"] is not None]
    stock_map: Dict[int, int] = dict(
        CurrentStock.objects.filter(item_id__in=item_ids).values_list(
            "item_id", "quantity"
        )
    )

    dept_stock_map: Dict[str, int] = {}
    if indent.department:
        from psmodule.department_stock.models import Stock as DepartmentStock

        dept_code = getattr(indent.department, "code", None)
        dept_lookup_values = []
        if dept_code:
            dept_lookup_values.append(f"dep_{dept_code.lower()}")
            dept_lookup_values.append(dept_code.lower())
        dept_lookup_values.append(f"dep_{indent.department.id}")
        dept_lookup_values.append(str(indent.department.id))

        dept_stock_map = {
            str(stock_name).strip().lower(): qty
            for stock_name, qty in DepartmentStock.objects.filter(
                department__in=[v for v in dept_lookup_values if v]
            ).values_list("stock_name", "quantity")
        }

    from psmodule.models import StoreItem
    item_name_map = dict(
        StoreItem.objects.filter(id__in=item_ids).values_list("id", "name")
    )

    breakdown: List[dict] = []
    for line in lines:
        requested = line["quantity"]
        item_id = line["item_id"]
        available = stock_map.get(item_id, 0)
        dept_available = 0
        item_name = item_name_map.get(item_id, "")
        if item_name:
            item_key = item_name.strip().lower()
            dept_available = dept_stock_map.get(item_key, 0)
            if dept_available == 0:
                for stock_name, qty in dept_stock_map.items():
                    if stock_name.lower() == item_key:
                        dept_available = qty
                        break

        best_available = max(available, dept_available)
        ok = best_available >= requested
        breakdown.append(
            {
                "item_id": item_id,
                "item_name": item_name,
                "requested_qty": requested,
                "available_qty": best_available,
                "ok": ok,
            }
        )

    return {
        "indent_id": indent.id,
        "all_available": all(b["ok"] for b in breakdown),
        "items": breakdown,
    }


def get_indents_for_actor_data(actor, *, request=None) -> List[dict]:
    qs = Indent.objects.select_related(
        "indenter",
        "indenter__user",
        "department",
        "current_approver",
        "current_approver__user",
    ).prefetch_related("items__item", "documents")
    if actor.role == ActingRole.EMPLOYEE:
        qs = qs.filter(indenter=actor.extrainfo)
    elif actor.role == ActingRole.PS_ADMIN:
        qs = qs.filter(
            status__in=[
                Indent.Status.EXTERNAL_PROCUREMENT,
                Indent.Status.APPROVED,
                Indent.Status.BIDDING,
                Indent.Status.PURCHASED,
                Indent.Status.STOCK_ENTRY,
                Indent.Status.STOCKED,
            ]
        )
    elif actor.role in (
        ActingRole.DEPADMIN,
        ActingRole.HOD,
        ActingRole.REGISTRAR,
        ActingRole.DIRECTOR,
    ):
        qs = qs.filter(current_approver=actor.extrainfo)
    else:
        raise PermissionDenied("Unauthorized")

    qs = qs.order_by("-updated_at")
    return IndentSerializer(qs, many=True, context={"request": request}).data


def get_indent_decisions_for_actor_data(actor, user, *, request=None) -> List[dict]:
    if actor.role == ActingRole.EMPLOYEE:
        raise PermissionDenied("Only approver roles can view decisions.")

    indent_ids = (
        IndentAudit.objects.filter(
            user=user,
            acting_role=actor.role,
            action__in=["APPROVE", "REJECT"],
        )
        .order_by("-created_at")
        .values_list("indent_id", flat=True)
        .distinct()
    )
    qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(id__in=indent_ids)
        .order_by("-updated_at")
    )
    return IndentSerializer(qs, many=True, context={"request": request}).data


def get_me_payload(user) -> dict:
    extrainfo = get_extrainfo_for_user(user)

    allowed = [ActingRole.EMPLOYEE]
    if has_designation(extrainfo, "depadmin"):
        allowed.append(ActingRole.DEPADMIN)
    if has_designation(extrainfo, "ps admin"):
        allowed.append(ActingRole.PS_ADMIN)
    if is_user_hod(extrainfo):
        allowed.append(ActingRole.HOD)
    if has_designation(extrainfo, "registrar"):
        allowed.append(ActingRole.REGISTRAR)
    if has_designation(extrainfo, "director"):
        allowed.append(ActingRole.DIRECTOR)

    return {
        "user": {"id": user.id, "username": user.username},
        "department": {
            "id": extrainfo.department_id,
            "code": extrainfo.department.code,
        },
        "allowed_roles": allowed,
    }


def get_store_item_stock_check_status(item_id: int, required: int) -> dict:
    item = StoreItem.objects.filter(id=item_id).first()
    if not item:
        raise ValidationError({"item_id": "Unknown item."})

    stock = CurrentStock.objects.filter(item=item).first()
    available = stock.quantity if stock else 0

    if available >= required:
        check_status = StockCheckStatus.AVAILABLE
    elif available > 0:
        check_status = StockCheckStatus.PARTIAL
    else:
        check_status = StockCheckStatus.NOT_AVAILABLE

    return {
        "item_id": item.id,
        "item_name": item.name,
        "available": available,
        "required": required,
        "status": check_status.value,
    }


def get_procurement_ready_indents_for_actor_data(actor, *, request=None) -> List[dict]:
    if actor.role not in (ActingRole.DEPADMIN, ActingRole.PS_ADMIN):
        raise PermissionDenied(
            "Only DepAdmin/PS Admin can view procurement-ready indents."
        )

    # PS Admin: APPROVED (pending PS workflow) + legacy EXTERNAL_PROCUREMENT.
    # DepAdmin: only EXTERNAL_PROCUREMENT — APPROVED indents are already routed to PS Admin.
    status_in = (
        [Indent.Status.EXTERNAL_PROCUREMENT, Indent.Status.APPROVED]
        if actor.role == ActingRole.PS_ADMIN
        else [Indent.Status.EXTERNAL_PROCUREMENT]
    )

    qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(status__in=status_in)
    )

    if actor.role == ActingRole.DEPADMIN:
        qs = qs.filter(department=actor.extrainfo.department)

    return IndentSerializer(
        qs.order_by("-updated_at"), many=True, context={"request": request}
    ).data


def get_indent_for_stock_entry(indent_id: int, actor) -> Indent:
    if actor.role not in (ActingRole.DEPADMIN, ActingRole.PS_ADMIN):
        raise PermissionDenied("Only DepAdmin/PS Admin can create stock entry.")

    indent = (
        Indent.objects.select_related("department")
        .prefetch_related("items")
        .filter(id=indent_id)
        .first()
    )
    if not indent:
        raise ValidationError({"detail": "Indent not found."})

    if indent.status != Indent.Status.PURCHASED:
        raise ValidationError(
            {"detail": "Stock entry is allowed only for purchased indents."}
        )

    if not indent.delivery_confirmed:
        raise ValidationError(
            {"detail": "Delivery must be confirmed before stock entry."}
        )

    if (
        actor.role == ActingRole.DEPADMIN
        and indent.department_id != actor.extrainfo.department_id
    ):
        raise PermissionDenied("Cannot create stock entry for another department.")

    return indent


def get_ps_admin_indents_by_category(actor, *, request=None) -> dict:
    """Get indents categorized by procurement stage for PS_ADMIN dashboard"""
    if actor.role != ActingRole.PS_ADMIN:
        raise PermissionDenied("Only PS_ADMIN can access this view.")

    # Pending: APPROVED indents ready for bidding
    pending_qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(status=Indent.Status.APPROVED)
        .order_by("-updated_at")
    )

    # Bidding: Indents in BIDDING status
    bidding_qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(status=Indent.Status.BIDDING)
        .order_by("-updated_at")
    )

    # Purchased: Indents in PURCHASED status (awaiting/confirmed delivery)
    purchased_qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(status=Indent.Status.PURCHASED)
        .order_by("-updated_at")
    )

    # Stock entry: Indents moved to stock entry stage
    stock_entry_qs = (
        Indent.objects.select_related(
            "indenter",
            "indenter__user",
            "department",
            "current_approver",
            "current_approver__user",
        )
        .prefetch_related("items__item", "documents")
        .filter(status__in=[Indent.Status.STOCK_ENTRY, Indent.Status.STOCKED])
        .order_by("-updated_at")
    )

    ctx = {"request": request}
    return {
        "pending": IndentSerializer(pending_qs, many=True, context=ctx).data,
        "bidding": IndentSerializer(bidding_qs, many=True, context=ctx).data,
        "purchased": IndentSerializer(purchased_qs, many=True, context=ctx).data,
        "stock_entry": IndentSerializer(stock_entry_qs, many=True, context=ctx).data,
    }


# --- Writes / ORM mutations (called from services) ---


def resolve_store_item_id_for_line(line: dict) -> int:
    if line.get("item_id") is not None:
        return int(line["item_id"])
    name = (line.get("item_name") or "").strip()
    if not name:
        raise ValidationError(
            {"items": "Each item line requires item_id or item_name."}
        )
    existing = StoreItem.objects.filter(name__iexact=name).first()
    if existing:
        return existing.id
    return StoreItem.objects.create(name=name[:255], unit="nos").id


def create_indent_entity(
    *,
    indenter,
    department,
    purpose: str,
    justification: str,
    estimated_cost,
    status: str,
    designation: str = "",
    date_of_request=None,
    why_requirement_needed: str = "",
    urgency_level: str = Indent.UrgencyLevel.MEDIUM,
    expected_usage: str = "",
    contacts=None,
) -> Indent:
    kwargs: dict = {
        "indenter": indenter,
        "department": department,
        "purpose": purpose or "",
        "justification": justification or "",
        "estimated_cost": estimated_cost,
        "status": status,
        "designation": designation or "",
        "why_requirement_needed": why_requirement_needed or "",
        "urgency_level": urgency_level or Indent.UrgencyLevel.MEDIUM,
        "expected_usage": expected_usage or "",
        "contacts": contacts if contacts is not None else [],
    }
    if date_of_request is not None:
        kwargs["date_of_request"] = date_of_request
    return Indent.objects.create(**kwargs)


def create_indent_line_items(indent: Indent, item_lines: list) -> None:
    for line in item_lines:
        item_id = resolve_store_item_id_for_line(line)
        qty = int(line["quantity"])
        unit_price = line.get("unit_price")
        est = line.get("estimated_cost")
        if est is None and unit_price is not None:
            est = (Decimal(str(unit_price)) * qty).quantize(Decimal("0.01"))
        item_obj = StoreItem.objects.get(pk=item_id)
        display_name = (line.get("item_name") or "").strip() or item_obj.name
        desc = line.get("item_description") or line.get("description") or ""
        cat = line.get("category") or ""
        IndentItem.objects.create(
            indent=indent,
            item_id=item_id,
            quantity=qty,
            estimated_cost=est,
            line_name=display_name[:255],
            line_description=str(desc) if desc else "",
            category=str(cat)[:120] if cat else "",
            unit_price=unit_price,
        )


def replace_indent_line_items(indent: Indent, item_lines: list) -> None:
    IndentItem.objects.filter(indent=indent).delete()
    if item_lines:
        create_indent_line_items(indent, item_lines)


def clear_indent_documents(indent: Indent) -> None:
    for doc in indent.documents.all():
        doc.file.delete(save=False)
        doc.delete()


def create_indent_audit_event(
    *,
    indent: Indent,
    user,
    acting_role: str,
    action: str,
    notes: str = "",
) -> IndentAudit:
    return IndentAudit.objects.create(
        indent=indent,
        user=user,
        acting_role=acting_role,
        action=action,
        notes=notes,
    )


def get_indent_by_id(indent_id: int) -> Indent:
    return Indent.objects.select_related("department").get(id=indent_id)


def get_indent_for_delivery_confirmation(indent_id: int, extrainfo) -> Optional[Indent]:
    return (
        Indent.objects.select_related("indenter")
        .filter(id=indent_id, indenter=extrainfo)
        .first()
    )


def create_stock_entry_with_line_map(
    *,
    indent: Indent,
    request_user,
    acting_role: str,
    notes: str,
    payload_map: dict[int, int],
) -> StockEntry:
    entry = StockEntry.objects.create(
        indent=indent,
        created_by=request_user,
        acting_role=acting_role,
        notes=notes or "",
    )
    for item_id, qty in payload_map.items():
        StockEntryItem.objects.create(
            stock_entry=entry, item_id=item_id, quantity=qty
        )
        stock, _ = CurrentStock.objects.get_or_create(
            item_id=item_id, defaults={"quantity": 0}
        )
        quantity_delta = qty
        if indent.procurement_type == Indent.ProcurementType.INTERNAL:
            quantity_delta = -qty
            if stock.quantity < qty:
                raise ValidationError(
                    {
                        "detail": (
                            f"Insufficient central stock for item_id {item_id} "
                            f"to complete internal stock entry."
                        )
                    }
                )
        stock.quantity += quantity_delta
        stock.save(update_fields=["quantity", "updated_at"])

    from psmodule.department_stock.selectors import (
        apply_received_quantities_to_department_stock,
    )

    apply_received_quantities_to_department_stock(
        getattr(indent.department, "code", None) or "",
        payload_map,
    )
    return entry


def create_stock_allocation_with_line_map(
    *,
    indent: Indent,
    request_user,
    acting_role: str,
    notes: str,
) -> StockAllocation:
    # Get the requested quantities from indent items
    payload_map = {
        line.item_id: line.quantity
        for line in indent.items.all()
        if line.item_id is not None
    }

    allocation = StockAllocation.objects.create(
        indent=indent,
        allocated_by=request_user,
        acting_role=acting_role,
        notes=notes or "",
    )
    for item_id, qty in payload_map.items():
        StockAllocationItem.objects.create(
            stock_allocation=allocation, item_id=item_id, quantity=qty
        )

    # Deduct actual stock from the proper source.
    internal_allocate_from_central_to_department(indent)

    return allocation


def create_stock_entry_from_indent_items_ps_admin(
    *,
    indent: Indent,
    request_user,
    acting_role: str,
    notes: str,
) -> StockEntry:
    entry = StockEntry.objects.create(
        indent=indent,
        created_by=request_user,
        acting_role=acting_role,
        notes=notes or "",
    )
    for item_line in indent.items.all():
        if not item_line.item_id:
            raise ValidationError(
                {
                    "detail": "All indent lines must reference a catalog item before stock entry."
                }
            )
        StockEntryItem.objects.create(
            stock_entry=entry,
            item_id=item_line.item_id,
            quantity=item_line.quantity,
        )
        stock, _ = CurrentStock.objects.get_or_create(
            item_id=item_line.item_id, defaults={"quantity": 0}
        )
        quantity_delta = item_line.quantity
        if indent.procurement_type == Indent.ProcurementType.INTERNAL:
            quantity_delta = -quantity_delta
            if stock.quantity < item_line.quantity:
                raise ValidationError(
                    {
                        "detail": (
                            f"Insufficient central stock for item_id {item_line.item_id} "
                            f"to complete internal stock entry."
                        )
                    }
                )
        stock.quantity += quantity_delta
        stock.save(update_fields=["quantity", "updated_at"])

    item_map = {
        int(line.item_id): int(line.quantity)
        for line in indent.items.all()
        if line.item_id is not None
    }
    from psmodule.department_stock.selectors import (
        apply_received_quantities_to_department_stock,
    )

    apply_received_quantities_to_department_stock(
        getattr(indent.department, "code", None) or "",
        item_map,
    )
    return entry


def internal_allocate_from_central_to_department(indent: Indent, is_issuing: bool = False) -> dict[int, int]:
    """
    Allocate items for internal procurement.
    
    For each item:
    - If available in central CurrentStock: decrement it and increment department stock
    - If available in department's own stock: no decrement needed (already in department)
    - Otherwise: raise validation error
    
    Caller must use transaction.atomic().
    """
    lines = list(indent.items.filter(item_id__isnull=False).select_related("item"))
    if not lines:
        raise ValidationError(
            {"detail": "Indent has no catalog lines to allocate from central stock."}
        )

    aggregated: dict[int, int] = {}
    for line in lines:
        iid = int(line.item_id)
        aggregated[iid] = aggregated.get(iid, 0) + int(line.quantity)

    # Get item ID to name mapping for department stock lookup
    item_name_map = {line.item_id: line.item.name for line in lines}
    
    # Get department code for department stock lookup
    dept_code = getattr(indent.department, "code", None) or ""
    dept_stock_map: Dict[str, int] = {}
    dept_stock_objects: dict[str, object] = {}
    if dept_code:
        from psmodule.department_stock.models import Stock as DepartmentStock
        dept_lookup_values = [
            f"dep_{dept_code.lower()}",
            dept_code.lower(),
            f"dep_{indent.department.id}",
            str(indent.department.id),
        ]
        for stock in DepartmentStock.objects.select_for_update().filter(
            department__in=[v for v in dept_lookup_values if v]
        ):
            stock_key = str(stock.stock_name).strip().lower()
            if not stock_key:
                continue
            dept_stock_map[stock_key] = stock.quantity
            dept_stock_objects[stock_key] = stock

    to_decrement_from_central: dict[int, int] = {}
    to_decrement_from_department: dict[int, tuple[object, int]] = {}

    for item_id, need in aggregated.items():
        item_name = item_name_map.get(item_id, "")

        # Check central stock first
        central_stock = (
            CurrentStock.objects.select_for_update()
            .filter(item_id=item_id)
            .first()
        )
        central_avail = central_stock.quantity if central_stock else 0

        # Resolve department stock by exact and case-insensitive item name
        dept_avail = 0
        dept_stock_obj = None
        if item_name:
            item_key = item_name.strip().lower()
            dept_stock_obj = dept_stock_objects.get(item_key)
            if dept_stock_obj is None:
                for stock_key, stock_obj in dept_stock_objects.items():
                    if stock_key.lower() == item_key:
                        dept_stock_obj = stock_obj
                        break
            if dept_stock_obj is not None:
                dept_avail = dept_stock_obj.quantity

        if central_avail >= need:
            # Central has enough: decrement from central
            to_decrement_from_central[item_id] = need
        elif dept_avail >= need:
            # Department has enough: decrement department stock directly
            to_decrement_from_department[item_id] = (dept_stock_obj, need)
        else:
            # Not enough in either location
            raise ValidationError(
                {
                    "detail": (
                        f"Insufficient stock for item_id {item_id} (need {need}, "
                        f"central: {central_avail}, department: {dept_avail})."
                    )
                }
            )

    # Decrement central stock for items that came from central
    for item_id, need in to_decrement_from_central.items():
        stock = (
            CurrentStock.objects.select_for_update()
            .filter(item_id=item_id)
            .first()
        )
        if stock:
            stock.quantity -= need
            stock.save(update_fields=["quantity", "updated_at"])

    # Decrement department stock for items fulfilled from department inventory
    for item_id, (dept_stock, need) in to_decrement_from_department.items():
        if dept_stock is not None:
            dept_stock.quantity -= need
            dept_stock.save(update_fields=["quantity"])

    # Update department stock for items that came from central
    if to_decrement_from_central:
        from psmodule.department_stock.selectors import (
            apply_received_quantities_to_department_stock,
        )
        sign = -1 if not is_issuing else 0
        apply_received_quantities_to_department_stock(
            dept_code,
            {item_id: sign * need for item_id, need in to_decrement_from_central.items()},
        )

    return aggregated


def save_indent(indent: Indent, update_fields: list[str]) -> None:
    indent.save(update_fields=update_fields)
