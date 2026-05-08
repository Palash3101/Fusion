from rest_framework import serializers

from psmodule.department_stock import selectors
from psmodule.department_stock.models import Stock, TransferRequest
from psmodule.department_stock.permissions import get_user_depadmin_role


class StockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = ["id", "stock_name", "department", "quantity"]


class TransferRequestSerializer(serializers.ModelSerializer):
    stock = StockSerializer(read_only=True)
    requested_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = TransferRequest
        fields = [
            "id",
            "stock",
            "requested_by",
            "requested_from",
            "requested_quantity",
            "status",
            "created_at",
        ]


class TransferRequestCreateSerializer(serializers.Serializer):
    stock_id = serializers.IntegerField()
    requested_from = serializers.CharField(max_length=50, required=False, allow_blank=True)
    requested_quantity = serializers.IntegerField(default=1, min_value=1)

    def validate(self, attrs):
        request = self.context.get("request")
        role = get_user_depadmin_role(request.user) if request else None

        if not role:
            raise serializers.ValidationError({"detail": "Access Denied"})

        try:
            stock = selectors.get_stock_by_pk(attrs["stock_id"])
        except Stock.DoesNotExist:
            raise serializers.ValidationError({"stock_id": "Stock not found."})

        requested_from = attrs.get("requested_from", "")
        if not requested_from:
            requested_from = f"depadmin_{stock.department.replace('dep_', '')}"
            attrs["requested_from"] = requested_from

        if not isinstance(requested_from, str) or not requested_from.startswith("depadmin_"):
            raise serializers.ValidationError({"requested_from": "Requested from must be a depadmin role."})

        if requested_from == role:
            raise serializers.ValidationError({"requested_from": "Cannot request from your own department."})

        supplier_department = requested_from.replace("depadmin_", "dep_")
        if stock.department != supplier_department:
            raise serializers.ValidationError({
                "requested_from": "Requested from must match the stock owner's department.",
            })

        requested_quantity = attrs.get("requested_quantity", 1)
        if requested_quantity < 1:
            raise serializers.ValidationError({"requested_quantity": "Quantity must be at least 1."})
        if requested_quantity > stock.quantity:
            raise serializers.ValidationError({
                "requested_quantity": "Requested quantity cannot exceed available stock quantity.",
            })

        if stock.department == role.replace("depadmin_", "dep_"):
            raise serializers.ValidationError({
                "stock_id": "Cannot request transfer for stock already in your department.",
            })

        return attrs
