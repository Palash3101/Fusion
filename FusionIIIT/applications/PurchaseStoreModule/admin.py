from django.contrib import admin

from psmodule.models import Indent, IndentDocument, IndentItem, StoreItem


@admin.register(StoreItem)
class StoreItemAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "unit")
    search_fields = ("name",)


class IndentItemInline(admin.TabularInline):
    model = IndentItem
    extra = 0


class IndentDocumentInline(admin.TabularInline):
    model = IndentDocument
    extra = 0


@admin.register(Indent)
class IndentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "public_reference_id",
        "purpose",
        "status",
        "department",
        "indenter",
        "date_of_request",
        "urgency_level",
        "created_at",
    )
    list_filter = ("status", "urgency_level", "department")
    search_fields = ("purpose", "public_reference_id", "indenter__user__username")
    inlines = (IndentItemInline, IndentDocumentInline)
