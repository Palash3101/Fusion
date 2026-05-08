from django.contrib import admin

from psmodule.department_stock.models import Stock, TransferLog, TransferRequest


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("id", "stock_name", "department")
    search_fields = ("stock_name", "department")


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "stock", "requested_by", "requested_from", "status", "created_at")
    list_filter = ("status", "requested_from")
    search_fields = ("stock__stock_name", "requested_by__username", "requested_from")


@admin.register(TransferLog)
class TransferLogAdmin(admin.ModelAdmin):
    list_display = ("id", "stock", "from_department", "to_department", "approved_by", "timestamp")
    list_filter = ("from_department", "to_department")
    search_fields = ("stock__stock_name", "approved_by__username")
