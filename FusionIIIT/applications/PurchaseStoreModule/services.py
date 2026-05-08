from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from psmodule.models import ActingRole, Indent, IndentDocument
from psmodule.api.serializers import StockEntrySerializer
from psmodule.selectors import (
    check_stock_availability_for_indent_id,
    clear_indent_documents,
    create_indent_audit_event,
    create_indent_entity,
    create_indent_line_items,
    create_stock_allocation_with_line_map,
    create_stock_entry_from_indent_items_ps_admin,
    create_stock_entry_with_line_map,
    get_department_depadmin,
    get_department_by_code,
    get_department_hod,
    get_first_holder_by_designation,
    get_indent_by_id,
    get_indent_data,
    get_indent_for_delivery_confirmation,
    get_indent_for_hod_action,
    get_indent_for_stock_check,
    get_indent_for_stock_entry,
    internal_allocate_from_central_to_department,
    replace_indent_line_items,
    save_indent,
    validate_store_item_ids,
)


def save_indent_attachments_from_payload(
    indent: Indent,
    documents: list | None,
    *,
    replace: bool = False,
) -> None:
    if documents is None:
        return
    if replace:
        clear_indent_documents(indent)
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        raw_b64 = doc.get("data") or doc.get("content_base64") or ""
        if not raw_b64:
            continue
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                {"documents": "Invalid base64 document payload."}
            ) from e
        if len(raw) > 15 * 1024 * 1024:
            raise ValidationError({"documents": "File too large (max 15MB)."})
        name = (doc.get("filename") or "attachment").strip() or "attachment"
        att = IndentDocument(indent=indent, original_filename=name[:255])
        att.file.save(name[:255], ContentFile(raw), save=True)


def _finalize_indent_submission(indent: Indent, actor, request_user) -> None:
    indent.stock_available = check_stock_availability_for_indent_id(indent.id)
    hod = get_department_hod(indent.department)
    indent.current_approver = hod if hod else get_department_depadmin(indent.department)
    indent.status = Indent.Status.SUBMITTED
    save_indent(
        indent,
        ["stock_available", "current_approver", "status", "updated_at"],
    )
    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action="SUBMIT",
        notes="",
    )


def create_indent(
    validated_data: Dict[str, Any],
    actor,
    request_user,
    *,
    request=None,
) -> dict:
    if actor.role != ActingRole.EMPLOYEE:
        raise ValidationError("Only employees can submit indents.")

    as_draft = validated_data.get("as_draft", False)
    item_lines = validated_data.get("items") or []

    indenter = actor.extrainfo
    department = indenter.department

    if as_draft:
        indent = create_indent_entity(
            indenter=indenter,
            department=department,
            purpose=validated_data.get("purpose") or "",
            justification=validated_data.get("justification", ""),
            estimated_cost=validated_data.get("estimated_cost"),
            status=Indent.Status.DRAFT,
            designation=validated_data.get("designation", ""),
            date_of_request=validated_data.get("date_of_request"),
            why_requirement_needed=validated_data.get("why_requirement_needed", ""),
            urgency_level=validated_data.get(
                "urgency_level", Indent.UrgencyLevel.MEDIUM
            ),
            expected_usage=validated_data.get("expected_usage", ""),
            contacts=validated_data.get("contacts"),
        )
        if item_lines:
            create_indent_line_items(indent, item_lines)
        save_indent_attachments_from_payload(
            indent, validated_data.get("documents"), replace=False
        )
        create_indent_audit_event(
            indent=indent,
            user=request_user,
            acting_role=actor.role,
            action="SAVE_DRAFT",
            notes="",
        )
        return get_indent_data(indent.id, request=request)

    item_ids_for_validation = [
        int(line["item_id"])
        for line in item_lines
        if line.get("item_id") is not None
    ]
    if item_ids_for_validation:
        validate_store_item_ids(item_ids_for_validation)

    indent = create_indent_entity(
        indenter=indenter,
        department=department,
        purpose=validated_data["purpose"],
        justification=validated_data.get("justification", ""),
        estimated_cost=validated_data.get("estimated_cost"),
        status=Indent.Status.SUBMITTED,
        designation=validated_data.get("designation", ""),
        date_of_request=validated_data.get("date_of_request"),
        why_requirement_needed=validated_data.get("why_requirement_needed", ""),
        urgency_level=validated_data.get(
            "urgency_level", Indent.UrgencyLevel.MEDIUM
        ),
        expected_usage=validated_data.get("expected_usage", ""),
        contacts=validated_data.get("contacts"),
    )

    create_indent_line_items(indent, item_lines)
    save_indent_attachments_from_payload(
        indent, validated_data.get("documents"), replace=False
    )

    _finalize_indent_submission(indent, actor, request_user)

    return get_indent_data(indent.id, request=request)


def update_indent_draft(
    indent_id: int,
    validated_data: Dict[str, Any],
    actor,
    request_user,
    *,
    request=None,
    documents_replace: list | None = None,
) -> dict:
    if actor.role != ActingRole.EMPLOYEE:
        raise PermissionDenied("Only employees can update drafts.")

    indent = Indent.objects.filter(pk=indent_id, indenter=actor.extrainfo).first()
    if not indent:
        raise ValidationError({"detail": "Indent not found."})
    if indent.status != Indent.Status.DRAFT:
        raise ValidationError({"detail": "Only draft indents can be updated this way."})

    update_fields: list[str] = []
    field_map = {
        "purpose": "purpose",
        "justification": "justification",
        "estimated_cost": "estimated_cost",
        "designation": "designation",
        "date_of_request": "date_of_request",
        "why_requirement_needed": "why_requirement_needed",
        "urgency_level": "urgency_level",
        "expected_usage": "expected_usage",
        "contacts": "contacts",
    }
    for key, attr in field_map.items():
        if key in validated_data and validated_data[key] is not None:
            setattr(indent, attr, validated_data[key])
            update_fields.append(attr)

    if update_fields:
        update_fields.append("updated_at")
        save_indent(indent, update_fields)

    if "items" in validated_data and validated_data["items"] is not None:
        replace_indent_line_items(indent, validated_data["items"])

    if documents_replace is not None:
        save_indent_attachments_from_payload(
            indent, documents_replace, replace=True
        )

    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action="UPDATE_DRAFT",
        notes="",
    )
    return get_indent_data(indent.id, request=request)


def submit_indent_from_draft(
    indent_id: int,
    actor,
    request_user,
    *,
    request=None,
) -> dict:
    if actor.role != ActingRole.EMPLOYEE:
        raise PermissionDenied("Only employees can submit indents.")

    indent = Indent.objects.filter(pk=indent_id, indenter=actor.extrainfo).first()
    if not indent:
        raise ValidationError({"detail": "Indent not found."})
    if indent.status != Indent.Status.DRAFT:
        raise ValidationError({"detail": "Only draft indents can be submitted."})

    lines = list(indent.items.all())
    if not lines:
        raise ValidationError({"items": "At least one item is required to submit."})

    item_ids_for_validation = [line.item_id for line in lines if line.item_id]
    if item_ids_for_validation:
        validate_store_item_ids(item_ids_for_validation)
    if any(line.item_id is None for line in lines):
        raise ValidationError(
            {
                "items": "All lines must resolve to a catalog item before submit "
                "(use item_id or item_name for each line)."
            }
        )

    _finalize_indent_submission(indent, actor, request_user)
    return get_indent_data(indent.id, request=request)


def delete_indent_draft(
    indent_id: int,
    actor,
    _request_user,
    *,
    request=None,
) -> None:
    if actor.role != ActingRole.EMPLOYEE:
        raise PermissionDenied("Only employees can delete drafts.")

    indent = Indent.objects.filter(pk=indent_id, indenter=actor.extrainfo).first()
    if not indent:
        raise ValidationError({"detail": "Indent not found."})
    if indent.status != Indent.Status.DRAFT:
        raise ValidationError({"detail": "Only draft indents can be deleted."})
    if indent.stock_entries.exists():
        raise ValidationError({"detail": "This draft cannot be deleted."})

    with transaction.atomic():
        clear_indent_documents(indent)
        indent.delete()


def apply_hod_action(
    indent_id: int,
    actor,
    action_name: str,
    notes: str = "",
    forward_to_department_code: Optional[str] = None,
    request_user=None,
) -> dict:
    indent = get_indent_for_hod_action(indent_id, actor)

    if action_name == "APPROVE":
        if actor.role == ActingRole.DEPADMIN:
            if indent.status not in (
                Indent.Status.FORWARDED,
                Indent.Status.STOCK_CHECKED,
            ):
                raise ValidationError(
                    {
                        "detail": (
                            "Only forwarded or stock-checked indents can be approved."
                        )
                    }
                )

            if indent.status == Indent.Status.STOCK_CHECKED:
                if indent.stock_available:
                    indent.procurement_type = Indent.ProcurementType.INTERNAL
                else:
                    indent.procurement_type = Indent.ProcurementType.EXTERNAL
            else:
                # Direct approval from FORWARDED: check if stock actually exists
                stock_exists = check_stock_availability_for_indent_id(indent.id)
                indent.stock_available = stock_exists
                indent.procurement_type = (
                    Indent.ProcurementType.INTERNAL
                    if stock_exists
                    else Indent.ProcurementType.EXTERNAL
                )

            indent.status = Indent.Status.APPROVED
            indent.current_approver = None
            save_indent(
                indent,
                [
                    "status",
                    "stock_available",
                    "procurement_type",
                    "current_approver",
                    "updated_at",
                ],
            )

        elif actor.role == ActingRole.HOD:
            next_approver = get_department_depadmin(indent.department)
            if not next_approver:
                raise ValidationError(
                    {"detail": "No DepAdmin found for this department."}
                )
            indent.current_approver = next_approver
            indent.status = Indent.Status.FORWARDED
            save_indent(indent, ["status", "current_approver", "updated_at"])

        elif actor.role == ActingRole.DIRECTOR:
            next_approver = get_first_holder_by_designation("registrar")
            if not next_approver:
                raise ValidationError({"detail": "No Registrar found to route to."})
            indent.current_approver = next_approver
            indent.status = Indent.Status.FORWARDED
            save_indent(indent, ["status", "current_approver", "updated_at"])

        elif actor.role == ActingRole.REGISTRAR:
            indent.status = Indent.Status.APPROVED
            indent.current_approver = None
            save_indent(indent, ["status", "current_approver", "updated_at"])
        else:
            raise ValidationError({"action": "Invalid approver role"})

    elif action_name == "ALLOCATE_STOCK":
        if actor.role != ActingRole.DEPADMIN:
            raise ValidationError({"detail": "Only Department Admin can allocate stock."})
        
        if indent.status not in (Indent.Status.FORWARDED, Indent.Status.STOCK_CHECKED):
            raise ValidationError(
                {"detail": "Only forwarded or stock-checked indents can be allocated."}
            )

        # Check stock availability
        stock_available = check_stock_availability_for_indent_id(indent.id)
        if not stock_available:
            raise ValidationError({"detail": "Insufficient stock available for allocation."})

        # Allocate stock
        allocation = create_stock_allocation(
            indent_id=indent.id,
            actor=actor,
            request_user=request_user,
            notes=notes,
        )

        indent.status = Indent.Status.STOCK_ALLOCATED
        indent.procurement_type = Indent.ProcurementType.INTERNAL
        indent.stock_available = True
        indent.current_approver = None
        save_indent(
            indent,
            ["status", "procurement_type", "stock_available", "current_approver", "updated_at"],
        )

    elif action_name == "REJECT":
        indent.status = Indent.Status.REJECTED
        indent.current_approver = None
        save_indent(indent, ["status", "current_approver", "updated_at"])

    elif action_name == "FORWARD":
        dept_code = (forward_to_department_code or "").strip()
        if dept_code:
            target_dept = get_department_by_code(dept_code)
            target_hod = get_department_hod(target_dept)
            indent.department = target_dept
            indent.current_approver = target_hod
            indent.status = (
                Indent.Status.FORWARDED if target_hod else Indent.Status.SUBMITTED
            )
            save_indent(
                indent,
                ["department", "current_approver", "status", "updated_at"],
            )
        else:
            if actor.role != ActingRole.DEPADMIN:
                raise PermissionDenied("Only DepAdmin can forward to Director.")
            next_approver = get_first_holder_by_designation("director")
            if not next_approver:
                raise ValidationError({"detail": "No Director found to forward to."})
            indent.current_approver = next_approver
            indent.status = Indent.Status.FORWARDED_TO_DIRECTOR
            save_indent(indent, ["current_approver", "status", "updated_at"])
    else:
        raise ValidationError({"action": "Invalid action"})

    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action=action_name,
        notes=notes,
    )

    return get_indent_data(indent.id)


def check_stock_action(indent_id: int, actor, request_user) -> dict:
    indent = get_indent_for_stock_check(indent_id, actor)

    indent.stock_available = check_stock_availability_for_indent_id(indent.id)
    indent.procurement_type = (
        Indent.ProcurementType.INTERNAL
        if indent.stock_available
        else Indent.ProcurementType.EXTERNAL
    )
    indent.status = Indent.Status.STOCK_CHECKED
    save_indent(
        indent,
        ["stock_available", "procurement_type", "status", "updated_at"],
    )

    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action="CHECK_STOCK",
        notes="",
    )

    return get_indent_data(indent.id)


def create_stock_entry(
    indent_id: int,
    actor,
    request_user,
    item_lines: list[dict],
    notes: str = "",
) -> dict:
    indent = get_indent_for_stock_entry(indent_id, actor)

    requested_map = {
        int(line.item_id): int(line.quantity)
        for line in indent.items.all()
        if line.item_id is not None
    }
    payload_map = {int(line["item_id"]): int(line["quantity"]) for line in item_lines}

    if set(requested_map.keys()) != set(payload_map.keys()):
        raise ValidationError(
            {"items": "Payload items must exactly match indent items."}
        )

    for item_id, qty in payload_map.items():
        if qty <= 0:
            raise ValidationError(
                {"items": f"Quantity must be > 0 for item_id {item_id}."}
            )
        if qty != requested_map[item_id]:
            raise ValidationError(
                {"items": f"Quantity mismatch for item_id {item_id}."}
            )

    with transaction.atomic():
        entry = create_stock_entry_with_line_map(
            indent=indent,
            request_user=request_user,
            acting_role=actor.role,
            notes=notes or "",
            payload_map=payload_map,
        )

        indent.status = Indent.Status.STOCK_ENTRY
        indent.current_approver = None
        save_indent(indent, ["status", "current_approver", "updated_at"])

        create_indent_audit_event(
            indent=indent,
            user=request_user,
            acting_role=actor.role,
            action="STOCK_ENTRY",
            notes=notes or "",
        )

    return {
        "indent": get_indent_data(indent.id),
        "stock_entry": StockEntrySerializer(entry).data,
    }


def create_stock_allocation(
    indent_id: int,
    actor,
    request_user,
    notes: str = "",
) -> StockAllocation:
    indent = get_indent_by_id(indent_id)
    
    with transaction.atomic():
        allocation = create_stock_allocation_with_line_map(
            indent=indent,
            request_user=request_user,
            acting_role=actor.role,
            notes=notes or "",
        )

        create_indent_audit_event(
            indent=indent,
            user=request_user,
            acting_role=actor.role,
            action="STOCK_ALLOCATION",
            notes=notes or "",
        )

    return allocation


def apply_ps_admin_action(
    indent_id: int,
    actor,
    action_name: str,
    notes: str = "",
    request_user=None,
) -> dict:
    """Handle PS_ADMIN actions: BIDDING, PURCHASE and STOCK_ENTRY."""
    if actor.role != ActingRole.PS_ADMIN:
        raise PermissionDenied("Only PS_ADMIN can perform this action.")

    indent = get_indent_by_id(indent_id)

    if action_name == "BIDDING":
        if indent.status != Indent.Status.APPROVED:
            raise ValidationError(
                {"detail": "Only APPROVED indents can move to BIDDING status."}
            )
        indent.status = Indent.Status.BIDDING
        save_indent(indent, ["status", "updated_at"])

    elif action_name == "PURCHASE":
        if indent.status not in (Indent.Status.APPROVED, Indent.Status.BIDDING):
            raise ValidationError(
                {
                    "detail": "Only APPROVED or BIDDING indents can be marked as PURCHASED."
                }
            )

        indent.status = Indent.Status.PURCHASED
        indent.delivery_confirmed = False
        indent.current_approver = None
        save_indent(
            indent,
            [
                "status",
                "delivery_confirmed",
                "current_approver",
                "updated_at",
            ],
        )

    elif action_name == "STOCK_ENTRY":
        if indent.status != Indent.Status.PURCHASED:
            raise ValidationError(
                {"detail": "Only PURCHASED indents can be moved to STOCK_ENTRY."}
            )

        if not indent.delivery_confirmed:
            raise ValidationError(
                {"detail": "Delivery must be confirmed by employee before stock entry."}
            )

        with transaction.atomic():
            create_stock_entry_from_indent_items_ps_admin(
                indent=indent,
                request_user=request_user,
                acting_role=actor.role,
                notes=notes or "",
            )

            indent.status = Indent.Status.STOCK_ENTRY
            indent.current_approver = None
            save_indent(indent, ["status", "current_approver", "updated_at"])

    elif action_name == "INTERNAL_ALLOCATE":
        if indent.status != Indent.Status.APPROVED:
            raise ValidationError(
                {"detail": "Only APPROVED indents can be allocated from central stock."}
            )
        if indent.procurement_type != Indent.ProcurementType.INTERNAL:
            raise ValidationError(
                {
                    "detail": "Only internal procurement indents can use this action."
                }
            )
        if not indent.stock_available:
            raise ValidationError(
                {"detail": "Stock is not marked available for this indent."}
            )

        with transaction.atomic():
            internal_allocate_from_central_to_department(indent, is_issuing=True)
            indent.status = Indent.Status.INTERNAL_ISSUED
            indent.delivery_confirmed = True
            indent.current_approver = None
            save_indent(
                indent,
                [
                    "status",
                    "delivery_confirmed",
                    "current_approver",
                    "updated_at",
                ],
            )

    else:
        raise ValidationError({"action": "Invalid action"})

    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action=action_name,
        notes=notes,
    )

    return get_indent_data(indent.id)


def confirm_delivery(indent_id: int, actor, request_user=None) -> dict:
    """Allow employees to confirm delivery for their purchased indents."""
    if actor.role != ActingRole.EMPLOYEE:
        raise PermissionDenied("Only employees can confirm delivery.")

    indent = get_indent_for_delivery_confirmation(indent_id, actor.extrainfo)
    if not indent:
        raise PermissionDenied("You can only confirm delivery for your own indents.")

    if indent.status != Indent.Status.PURCHASED:
        raise ValidationError(
            {"detail": "Delivery can only be confirmed for PURCHASED indents."}
        )

    if indent.delivery_confirmed:
        raise ValidationError({"detail": "Delivery is already confirmed."})

    indent.delivery_confirmed = True
    save_indent(indent, ["delivery_confirmed", "updated_at"])

    create_indent_audit_event(
        indent=indent,
        user=request_user,
        acting_role=actor.role,
        action="CONFIRM_DELIVERY",
        notes="",
    )

    return get_indent_data(indent.id)
