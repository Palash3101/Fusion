from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from psmodule.models import (
    Indent,
    IndentDocument,
    IndentItem,
    StockAllocation,
    StockAllocationItem,
    StockEntry,
    StockEntryItem,
    StoreItem,
)


def validate_stock_check_query_params(query_params) -> int:
    required = query_params.get("required")
    if required is None:
        raise ValidationError({"required": "Query param required is required."})
    try:
        required_int = int(required)
    except ValueError as e:
        raise ValidationError({"required": "Must be an integer."}) from e
    if required_int < 0:
        raise ValidationError({"required": "Must be >= 0."})
    return required_int


class StoreItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreItem
        fields = ["id", "name", "unit"]


class IndentDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = IndentDocument
        fields = ["id", "url", "original_filename", "uploaded_at"]
        read_only_fields = fields

    def get_url(self, obj: IndentDocument) -> str | None:
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class IndentItemWriteSerializer(serializers.Serializer):
    item_id = serializers.IntegerField(required=False, allow_null=True)
    item_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1)
    estimated_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    item_description = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    category = serializers.CharField(required=False, allow_blank=True, default="")
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, allow_null=True
    )

    def validate(self, attrs):
        if attrs.get("item_id") is None and not (attrs.get("item_name") or "").strip():
            raise serializers.ValidationError(
                "Each line requires either item_id or item_name."
            )
        return attrs


class IndentItemReadSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()
    item_description = serializers.CharField(source="line_description", read_only=True)
    line_total = serializers.SerializerMethodField()
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = IndentItem
        fields = [
            "id",
            "item",
            "item_id",
            "item_name",
            "item_description",
            "category",
            "quantity",
            "unit_price",
            "estimated_cost",
            "line_total",
        ]

    def get_item(self, obj: IndentItem):
        if obj.item_id:
            return StoreItemSerializer(obj.item, context=self.context).data
        return None

    def get_item_name(self, obj: IndentItem) -> str:
        if obj.line_name:
            return obj.line_name
        if obj.item_id:
            return obj.item.name
        return ""

    def get_line_total(self, obj: IndentItem) -> str:
        if obj.estimated_cost is not None:
            return str(obj.estimated_cost)
        if obj.unit_price is not None:
            total = (Decimal(obj.unit_price) * obj.quantity).quantize(Decimal("0.01"))
            return str(total)
        return "0.00"


class IndentSerializer(serializers.ModelSerializer):
    items = IndentItemReadSerializer(many=True, read_only=True)
    documents = IndentDocumentSerializer(many=True, read_only=True)
    grand_total = serializers.SerializerMethodField()
    department_detail = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()

    class Meta:
        model = Indent
        fields = [
            "id",
            "public_reference_id",
            "date_of_request",
            "purpose",
            "justification",
            "why_requirement_needed",
            "urgency_level",
            "expected_usage",
            "designation",
            "contacts",
            "estimated_cost",
            "status",
            "delivery_confirmed",
            "stock_available",
            "procurement_type",
            "department",
            "department_detail",
            "requested_by",
            "current_approver",
            "created_at",
            "updated_at",
            "items",
            "documents",
            "grand_total",
        ]
        read_only_fields = [
            "public_reference_id",
            "date_of_request",
            "purpose",
            "justification",
            "designation",
            "contacts",
            "why_requirement_needed",
            "urgency_level",
            "expected_usage",
            "estimated_cost",
            "status",
            "delivery_confirmed",
            "stock_available",
            "procurement_type",
            "department",
            "current_approver",
            "created_at",
            "updated_at",
        ]

    def get_grand_total(self, obj: Indent) -> str:
        total = Decimal("0")
        for line in obj.items.all():
            if line.estimated_cost is not None:
                total += Decimal(line.estimated_cost)
            elif line.unit_price is not None:
                total += (Decimal(line.unit_price) * line.quantity).quantize(
                    Decimal("0.01")
                )
        return str(total.quantize(Decimal("0.01")))

    def get_department_detail(self, obj: Indent) -> dict:
        d = obj.department
        return {"id": d.id, "code": d.code, "name": d.name}

    def get_requested_by(self, obj: Indent) -> dict:
        u = obj.indenter.user
        return {
            "id": u.id,
            "username": u.username,
            "employee_id": obj.indenter.employee_id,
        }


class DocumentUploadSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255, required=False, allow_blank=True)
    data = serializers.CharField(required=False, allow_blank=True)


class IndentCreateSerializer(serializers.Serializer):
    purpose = serializers.CharField(max_length=255, required=False, allow_blank=True)
    justification = serializers.CharField(allow_blank=True, required=False)
    estimated_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    items = IndentItemWriteSerializer(many=True, required=False)
    as_draft = serializers.BooleanField(default=False, required=False)

    designation = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    date_of_request = serializers.DateField(required=False, allow_null=True)
    why_requirement_needed = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    urgency_level = serializers.ChoiceField(
        choices=Indent.UrgencyLevel.choices,
        default=Indent.UrgencyLevel.MEDIUM,
        required=False,
    )
    expected_usage = serializers.CharField(required=False, allow_blank=True, default="")
    contacts = serializers.ListField(child=serializers.DictField(), required=False)
    documents = serializers.ListField(child=serializers.DictField(), required=False)

    def validate_contacts(self, value):
        if value is None:
            return []
        if not value:
            return []
        for row in value:
            if not isinstance(row, dict):
                raise serializers.ValidationError("Each contact must be an object.")
        return value

    def validate(self, attrs):
        as_draft = attrs.get("as_draft", False)
        purpose = (attrs.get("purpose") or "").strip()
        if not as_draft and not purpose:
            raise serializers.ValidationError(
                {"purpose": "Purpose is required when submitting."}
            )
        attrs["purpose"] = purpose or attrs.get("purpose", "")
        if attrs.get("contacts") is None:
            attrs["contacts"] = []
        items = attrs.get("items")
        if not as_draft:
            if not items:
                raise serializers.ValidationError(
                    {"items": "At least one item is required."}
                )
        return attrs

    def validate_items(self, items):
        if items is None:
            return []
        if not items:
            return items
        for row in items:
            ser = IndentItemWriteSerializer(data=row)
            ser.is_valid(raise_exception=True)
        seen_ids = []
        for i in items:
            if i.get("item_id") is not None:
                seen_ids.append(int(i["item_id"]))
        if len(seen_ids) != len(set(seen_ids)):
            raise serializers.ValidationError(
                "Duplicate item_id entries are not allowed."
            )
        return items


class IndentPartialUpdateSerializer(serializers.Serializer):
    purpose = serializers.CharField(max_length=255, required=False, allow_blank=True)
    justification = serializers.CharField(required=False, allow_blank=True)
    estimated_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    designation = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    date_of_request = serializers.DateField(required=False, allow_null=True)
    why_requirement_needed = serializers.CharField(required=False, allow_blank=True)
    urgency_level = serializers.ChoiceField(
        choices=Indent.UrgencyLevel.choices, required=False
    )
    expected_usage = serializers.CharField(required=False, allow_blank=True)
    contacts = serializers.ListField(child=serializers.DictField(), required=False)
    items = IndentItemWriteSerializer(many=True, required=False)
    documents = serializers.ListField(child=serializers.DictField(), required=False)


class HODActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["APPROVE", "REJECT", "FORWARD", "ALLOCATE_STOCK"])
    notes = serializers.CharField(required=False, allow_blank=True)
    forward_to_department_code = serializers.CharField(required=False, allow_blank=True)


class StockEntryItemWriteSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class StockEntryCreateSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)
    items = StockEntryItemWriteSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("At least one item is required.")
        item_ids = [i["item_id"] for i in items]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError("Duplicate item entries are not allowed.")
        return items


class PSAdminActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["BIDDING", "PURCHASE", "STOCK_ENTRY", "INTERNAL_ALLOCATE"]
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class StockEntryItemSerializer(serializers.ModelSerializer):
    item = StoreItemSerializer()

    class Meta:
        model = StockEntryItem
        fields = ["id", "item", "quantity"]


class StockEntrySerializer(serializers.ModelSerializer):
    items = StockEntryItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockEntry
        fields = ["id", "indent", "acting_role", "notes", "created_at", "items"]


class StockAllocationItemSerializer(serializers.ModelSerializer):
    item = StoreItemSerializer()

    class Meta:
        model = StockAllocationItem
        fields = ["id", "item", "quantity"]


class StockAllocationSerializer(serializers.ModelSerializer):
    items = StockAllocationItemSerializer(many=True, read_only=True)

    class Meta:
        model = StockAllocation
        fields = ["id", "indent", "acting_role", "notes", "created_at", "items"]
