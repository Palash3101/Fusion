from rest_framework import serializers  # type: ignore
from applications.ps1.models import (
    IndentFile, IndentItem, StockEntry, StockItem, StockTransfer,
    Vendor, GoodsReceivedNote, ProductReturn, Tender, TenderBid,
    StockReservation, AuditLog
)
from applications.globals.models import ExtraInfo, HoldsDesignation
from applications.filetracking.models import File, Tracking


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = '__all__'


class IndentItemSerializer(serializers.ModelSerializer):
    """
    Enhanced with Assignment 7 validations:
    - T-06: Field-level validation for mandatory fields
    - T-07: Min value validators
    """
    class Meta:
        model = IndentItem
        fields = (
            'id', 'indent_file', 'item_name', 'quantity', 'present_stock',
            'estimated_cost', 'purpose', 'specification', 'item_type',
            'item_subtype', 'nature', 'indigenous', 'replaced',
            'budgetary_head', 'expected_delivery', 'sources_of_supply',
        )

    def validate_quantity(self, value):
        """T-07: Ensure quantity >= 1"""
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1")
        return value

    def validate_estimated_cost(self, value):
        """T-07: Ensure cost > 0"""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Estimated cost must be greater than 0")
        return value

    def validate(self, data):
        """T-06: Validate all mandatory fields"""
        required_fields = [
            'item_name', 'quantity', 'purpose', 'specification',
            'item_type', 'budgetary_head', 'expected_delivery', 'sources_of_supply'
        ]

        errors = {}
        for field in required_fields:
            if field not in data or not data[field]:
                errors[field] = f"{field.replace('_', ' ').title()} is required"

        if errors:
            raise serializers.ValidationError(errors)

        return data


class IndentFileSerializer(serializers.ModelSerializer):
    """
    Enhanced with Assignment 7 fields:
    - T-01: Status, cancellation tracking
    - T-02: Rejection tracking
    """
    items = IndentItemSerializer(many=True, read_only=True)

    class Meta:
        model = IndentFile
        fields = '__all__'
        read_only_fields = ('cancelled_by', 'cancelled_at', 'rejected_by', 'rejected_at')


class ExtraInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtraInfo
        fields = '__all__'


class HoldsDesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = HoldsDesignation
        fields = '__all__'


class TrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tracking
        fields = '__all__'


class VendorSerializer(serializers.ModelSerializer):
    """T-09: Vendor master serializer"""
    class Meta:
        model = Vendor
        fields = (
            'id', 'vendor_code', 'vendor_name', 'contact_person',
            'email', 'phone', 'address', 'is_approved', 'gst_number',
            'pan_number', 'rating', 'total_orders', 'created_at', 'updated_at'
        )
        read_only_fields = ('rating', 'total_orders', 'created_at', 'updated_at')

    def validate_gst_number(self, value):
        """Validate GST number format"""
        if value and len(value) != 15:
            raise serializers.ValidationError("GST number must be 15 characters")
        return value

    def validate_pan_number(self, value):
        """Validate PAN number format"""
        if value and len(value) != 10:
            raise serializers.ValidationError("PAN number must be 10 characters")
        return value


class StockEntrySerializer(serializers.ModelSerializer):
    """Enhanced with vendor ForeignKey (T-09)"""
    vendor_details = VendorSerializer(source='vendor', read_only=True)

    class Meta:
        model = StockEntry
        fields = (
            'item_id', 'dealing_assistant_id', 'vendor', 'vendor_details',
            'current_stock', 'recieved_date', 'bill', 'location',
            'is_capital_asset', 'capitalization_threshold',
        )


class StockItemSerializer(serializers.ModelSerializer):
    """Enhanced with asset tag (T-16)"""
    class Meta:
        model = StockItem
        fields = (
            'id', 'StockEntryId', 'nomenclature', 'inUse',
            'department', 'location', 'isTransferred', 'asset_tag',
        )
        read_only_fields = ('nomenclature', 'asset_tag')


class StockTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransfer
        fields = '__all__'


class StockReservationSerializer(serializers.ModelSerializer):
    """T-13: Stock reservation serializer"""
    class Meta:
        model = StockReservation
        fields = (
            'id', 'stock_item', 'indent_file', 'quantity',
            'reserved_by', 'reserved_at', 'expires_at', 'is_active',
        )
        read_only_fields = ('reserved_at',)


class GoodsReceivedNoteSerializer(serializers.ModelSerializer):
    """T-04: GRN serializer"""
    class Meta:
        model = GoodsReceivedNote
        fields = (
            'id', 'grn_number', 'indent_file', 'stock_entry',
            'received_by', 'confirmed_by', 'received_date', 'confirmed_date',
            'quantity_received', 'quantity_accepted', 'quality_check_passed',
            'remarks', 'has_discrepancy', 'discrepancy_details',
            'invoice_release_approved',
        )
        read_only_fields = ('grn_number', 'received_date')


class ProductReturnSerializer(serializers.ModelSerializer):
    """T-05: Product return serializer"""
    class Meta:
        model = ProductReturn
        fields = (
            'id', 'return_number', 'grn', 'stock_entry', 'return_reason',
            'quantity_returned', 'return_initiated_by', 'return_date',
            'has_discrepancy', 'discrepancy_type', 'discrepancy_description',
            'status', 'resolution_type', 'resolved_by', 'resolved_at',
            'resolution_remarks', 'invoice_hold', 'invoice_hold_released',
        )
        read_only_fields = ('return_number', 'return_date')


class TenderBidSerializer(serializers.ModelSerializer):
    """T-08: Tender bid serializer"""
    vendor_details = VendorSerializer(source='vendor', read_only=True)

    class Meta:
        model = TenderBid
        fields = (
            'id', 'tender', 'vendor', 'vendor_details', 'bid_amount',
            'bid_document', 'technical_compliance', 'submitted_at',
            'evaluated', 'evaluation_score', 'evaluation_remarks', 'is_winner',
        )
        read_only_fields = ('submitted_at',)


class TenderSerializer(serializers.ModelSerializer):
    """T-08: Tender serializer"""
    bids = TenderBidSerializer(many=True, read_only=True)

    class Meta:
        model = Tender
        fields = (
            'id', 'tender_number', 'indent_file', 'title', 'description',
            'estimated_value', 'publish_date', 'bid_submission_deadline',
            'bid_opening_date', 'status', 'awarded_to', 'awarded_amount',
            'awarded_at', 'created_by', 'created_at', 'updated_at', 'bids',
        )
        read_only_fields = ('tender_number', 'created_at', 'updated_at')


class AuditLogSerializer(serializers.ModelSerializer):
    """T-23: Audit log serializer"""
    class Meta:
        model = AuditLog
        fields = (
            'id', 'timestamp', 'user', 'action', 'entity_type',
            'entity_id', 'old_value', 'new_value', 'ip_address', 'user_agent',
        )
        read_only_fields = ('timestamp',)
