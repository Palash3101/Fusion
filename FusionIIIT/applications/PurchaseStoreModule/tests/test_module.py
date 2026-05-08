from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from psmodule.accounts.models import DepartmentInfo, Designation, ExtraInfo, HoldsDesignation
from psmodule.models import (
    ActingRole,
    CurrentStock,
    Indent,
    IndentAudit,
    IndentItem,
    StockEntry,
    StoreItem,
)
from psmodule.department_stock.models import Stock as DepartmentStock
from psmodule.services import (
    apply_hod_action,
    apply_ps_admin_action,
    confirm_delivery,
    create_stock_entry,
    delete_indent_draft,
)
from psmodule.selectors import (
    get_ps_admin_indents_by_category,
    get_stock_breakdown_data,
)


class WorkflowPs002StockEntryTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.dept = DepartmentInfo.objects.create(code="CSE", name="Computer Science")
        self.other_dept = DepartmentInfo.objects.create(code="ECE", name="Electronics")

        self.depadmin_designation = Designation.objects.create(name="DepAdmin CSE")
        self.ps_admin_designation = Designation.objects.create(name="PS Admin")

        self.depadmin_user = User.objects.create_user(
            username="depadmin", password="pass1234"
        )
        self.ps_admin_user = User.objects.create_user(
            username="psadmin", password="pass1234"
        )
        self.employee_user = User.objects.create_user(
            username="employee", password="pass1234"
        )

        self.depadmin_info = ExtraInfo.objects.create(
            user=self.depadmin_user, department=self.dept, employee_id="depadmin"
        )
        self.ps_admin_info = ExtraInfo.objects.create(
            user=self.ps_admin_user, department=self.dept, employee_id="psadmin"
        )
        self.employee_info = ExtraInfo.objects.create(
            user=self.employee_user, department=self.dept, employee_id="employee"
        )

        HoldsDesignation.objects.create(
            designation=self.depadmin_designation,
            working=self.depadmin_info,
            is_active=True,
        )
        HoldsDesignation.objects.create(
            designation=self.ps_admin_designation,
            working=self.ps_admin_info,
            is_active=True,
        )

        self.item1 = StoreItem.objects.create(name="Pen", unit="nos")
        self.item2 = StoreItem.objects.create(name="A4 Paper", unit="ream")
        CurrentStock.objects.create(item=self.item1, quantity=10)
        CurrentStock.objects.create(item=self.item2, quantity=3)

        self.indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Procure stationery",
            status=Indent.Status.PURCHASED,
            delivery_confirmed=True,
        )
        IndentItem.objects.create(indent=self.indent, item=self.item1, quantity=5)
        IndentItem.objects.create(indent=self.indent, item=self.item2, quantity=2)

        DepartmentStock.objects.create(
            stock_name="Pen", department="dep_cse", quantity=100
        )
        DepartmentStock.objects.create(
            stock_name="A4 Paper", department="dep_cse", quantity=50
        )

    def _actor(self, role, extrainfo):
        return SimpleNamespace(role=role, extrainfo=extrainfo)

    def test_ps_admin_can_create_stock_entry_and_increase_inventory(self):
        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)

        result = create_stock_entry(
            indent_id=self.indent.id,
            actor=actor,
            request_user=self.ps_admin_user,
            item_lines=[
                {"item_id": self.item1.id, "quantity": 5},
                {"item_id": self.item2.id, "quantity": 2},
            ],
            notes="Goods received from supplier",
        )

        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.STOCK_ENTRY)

        stock1 = CurrentStock.objects.get(item=self.item1)
        stock2 = CurrentStock.objects.get(item=self.item2)
        self.assertEqual(stock1.quantity, 15)
        self.assertEqual(stock2.quantity, 5)

        self.assertEqual(StockEntry.objects.count(), 1)
        entry = StockEntry.objects.first()
        self.assertEqual(entry.acting_role, ActingRole.PS_ADMIN)
        self.assertEqual(entry.items.count(), 2)
        self.assertEqual(
            IndentAudit.objects.filter(
                indent=self.indent, action="STOCK_ENTRY"
            ).count(),
            1,
        )
        self.assertEqual(result["indent"]["status"], Indent.Status.STOCK_ENTRY)

    def test_ps_admin_internal_stock_entry_decreases_current_stock(self):
        internal_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Internal stock entry",
            status=Indent.Status.PURCHASED,
            delivery_confirmed=True,
            procurement_type=Indent.ProcurementType.INTERNAL,
        )
        IndentItem.objects.create(indent=internal_indent, item=self.item1, quantity=4)
        CurrentStock.objects.filter(item=self.item1).update(quantity=20)

        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)
        result = create_stock_entry(
            indent_id=internal_indent.id,
            actor=actor,
            request_user=self.ps_admin_user,
            item_lines=[{"item_id": self.item1.id, "quantity": 4}],
            notes="Allocate from warehouse",
        )

        internal_indent.refresh_from_db()
        self.assertEqual(internal_indent.status, Indent.Status.STOCK_ENTRY)
        self.assertEqual(CurrentStock.objects.get(item=self.item1).quantity, 16)
        self.assertEqual(StockEntry.objects.filter(indent=internal_indent).count(), 1)
        self.assertEqual(result["indent"]["status"], Indent.Status.STOCK_ENTRY)

        self.assertEqual(
            IndentAudit.objects.filter(
                indent=internal_indent, action="STOCK_ENTRY"
            ).count(),
            1,
        )

        self.assertEqual(result["stock_entry"]["acting_role"], ActingRole.PS_ADMIN)

    def test_reject_when_delivery_not_confirmed(self):
        self.indent.delivery_confirmed = False
        self.indent.save(update_fields=["delivery_confirmed", "updated_at"])

        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)

        with self.assertRaises(ValidationError):
            create_stock_entry(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.ps_admin_user,
                item_lines=[
                    {"item_id": self.item1.id, "quantity": 5},
                    {"item_id": self.item2.id, "quantity": 2},
                ],
            )

    def test_depadmin_cannot_create_stock_entry_for_other_department(self):
        other_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.other_dept,
            purpose="Other dept indent",
            status=Indent.Status.PURCHASED,
            delivery_confirmed=True,
        )
        IndentItem.objects.create(indent=other_indent, item=self.item1, quantity=1)

        actor = self._actor(ActingRole.DEPADMIN, self.depadmin_info)

        with self.assertRaises(PermissionDenied):
            create_stock_entry(
                indent_id=other_indent.id,
                actor=actor,
                request_user=self.depadmin_user,
                item_lines=[{"item_id": self.item1.id, "quantity": 1}],
            )

    def test_reject_when_payload_item_ids_do_not_match_indent(self):
        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)

        with self.assertRaises(ValidationError):
            create_stock_entry(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.ps_admin_user,
                item_lines=[{"item_id": self.item1.id, "quantity": 5}],
            )

        self.assertEqual(StockEntry.objects.count(), 0)

    def test_reject_when_quantity_mismatch(self):
        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)

        with self.assertRaises(ValidationError):
            create_stock_entry(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.ps_admin_user,
                item_lines=[
                    {"item_id": self.item1.id, "quantity": 4},
                    {"item_id": self.item2.id, "quantity": 2},
                ],
            )

        self.assertEqual(CurrentStock.objects.get(item=self.item1).quantity, 10)
        self.assertEqual(StockEntry.objects.count(), 0)

    def test_reject_when_indent_status_not_procurement_ready(self):
        self.indent.status = Indent.Status.REJECTED
        self.indent.save(update_fields=["status", "updated_at"])

        actor = self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)

        with self.assertRaises(ValidationError):
            create_stock_entry(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.ps_admin_user,
                item_lines=[
                    {"item_id": self.item1.id, "quantity": 5},
                    {"item_id": self.item2.id, "quantity": 2},
                ],
            )

    def test_employee_cannot_create_stock_entry(self):
        actor = self._actor(ActingRole.EMPLOYEE, self.employee_info)

        with self.assertRaises(PermissionDenied):
            create_stock_entry(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.employee_user,
                item_lines=[
                    {"item_id": self.item1.id, "quantity": 5},
                    {"item_id": self.item2.id, "quantity": 2},
                ],
            )


class WorkflowPsDeliveryConfirmationTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.dept = DepartmentInfo.objects.create(code="ME", name="Mechanical")
        self.other_dept = DepartmentInfo.objects.create(code="CE", name="Civil")

        self.employee_user = User.objects.create_user(
            username="employee2", password="pass1234"
        )
        self.other_user = User.objects.create_user(
            username="employee3", password="pass1234"
        )

        self.employee_info = ExtraInfo.objects.create(
            user=self.employee_user, department=self.dept, employee_id="employee2"
        )
        self.other_info = ExtraInfo.objects.create(
            user=self.other_user, department=self.other_dept, employee_id="employee3"
        )

        self.indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Confirm delivery flow",
            status=Indent.Status.PURCHASED,
            delivery_confirmed=False,
        )

    def _actor(self, role, extrainfo):
        return SimpleNamespace(role=role, extrainfo=extrainfo)

    def test_employee_can_confirm_delivery_for_own_purchased_indent(self):
        actor = self._actor(ActingRole.EMPLOYEE, self.employee_info)

        data = confirm_delivery(
            indent_id=self.indent.id,
            actor=actor,
            request_user=self.employee_user,
        )

        self.indent.refresh_from_db()
        self.assertTrue(self.indent.delivery_confirmed)
        self.assertEqual(data["delivery_confirmed"], True)

    def test_employee_cannot_confirm_delivery_for_other_users_indent(self):
        actor = self._actor(ActingRole.EMPLOYEE, self.other_info)

        with self.assertRaises(PermissionDenied):
            confirm_delivery(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.other_user,
            )

    def test_delivery_confirmation_requires_purchased_state(self):
        self.indent.status = Indent.Status.BIDDING
        self.indent.save(update_fields=["status", "updated_at"])
        actor = self._actor(ActingRole.EMPLOYEE, self.employee_info)

        with self.assertRaises(ValidationError):
            confirm_delivery(
                indent_id=self.indent.id,
                actor=actor,
                request_user=self.employee_user,
            )


class DeleteDraftIndentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.dept = DepartmentInfo.objects.create(code="CSE", name="Computer Science")
        self.employee_user = User.objects.create_user(username="emp_del", password="pass1234")
        self.other_user = User.objects.create_user(username="other_del", password="pass1234")
        self.employee_info = ExtraInfo.objects.create(
            user=self.employee_user, department=self.dept, employee_id="emp_del"
        )
        self.other_info = ExtraInfo.objects.create(
            user=self.other_user, department=self.dept, employee_id="other_del"
        )
        self.draft = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Draft to delete",
            status=Indent.Status.DRAFT,
        )

    def _actor(self, role, extrainfo):
        return SimpleNamespace(role=role, extrainfo=extrainfo)

    def test_employee_deletes_own_draft(self):
        actor = self._actor(ActingRole.EMPLOYEE, self.employee_info)
        pk = self.draft.id
        delete_indent_draft(pk, actor, self.employee_user)
        self.assertFalse(Indent.objects.filter(pk=pk).exists())

    def test_cannot_delete_submitted_indent(self):
        self.draft.status = Indent.Status.SUBMITTED
        self.draft.save(update_fields=["status", "updated_at"])
        actor = self._actor(ActingRole.EMPLOYEE, self.employee_info)
        with self.assertRaises(ValidationError):
            delete_indent_draft(self.draft.id, actor, self.employee_user)

    def test_other_employee_cannot_delete_draft(self):
        actor = self._actor(ActingRole.EMPLOYEE, self.other_info)
        with self.assertRaises(ValidationError):
            delete_indent_draft(self.draft.id, actor, self.other_user)


class DepadminInternalProcurementTests(TestCase):
    """DepAdmin approve with stock → APPROVED INTERNAL; PS Admin INTERNAL_ALLOCATE completes."""

    def setUp(self):
        User = get_user_model()
        self.dept = DepartmentInfo.objects.create(code="CSE", name="Computer Science")
        self.depadmin_designation = Designation.objects.create(name="DepAdmin CSE")
        self.ps_admin_designation = Designation.objects.create(name="PS Admin")
        self.depadmin_user = User.objects.create_user(username="da_int", password="pass1234")
        self.ps_admin_user = User.objects.create_user(username="ps_int", password="pass1234")
        self.employee_user = User.objects.create_user(username="emp_int", password="pass1234")
        self.depadmin_info = ExtraInfo.objects.create(
            user=self.depadmin_user, department=self.dept, employee_id="da_int"
        )
        self.ps_admin_info = ExtraInfo.objects.create(
            user=self.ps_admin_user, department=self.dept, employee_id="ps_int"
        )
        self.employee_info = ExtraInfo.objects.create(
            user=self.employee_user, department=self.dept, employee_id="emp_int"
        )
        HoldsDesignation.objects.create(
            designation=self.depadmin_designation,
            working=self.depadmin_info,
            is_active=True,
        )
        HoldsDesignation.objects.create(
            designation=self.ps_admin_designation,
            working=self.ps_admin_info,
            is_active=True,
        )
        self.item1 = StoreItem.objects.create(name="Pen", unit="nos")
        CurrentStock.objects.create(item=self.item1, quantity=20)
        self.indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Internal procurement",
            status=Indent.Status.STOCK_CHECKED,
            stock_available=True,
            procurement_type=Indent.ProcurementType.INTERNAL,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=self.indent, item=self.item1, quantity=3)
        DepartmentStock.objects.create(
            stock_name="Pen", department="dep_cse", quantity=5
        )

    def _actor(self, role, extrainfo):
        return SimpleNamespace(role=role, extrainfo=extrainfo)

    def test_depadmin_approve_internal_sets_approved_and_internal_type(self):
        apply_hod_action(
            self.indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )
        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.APPROVED)
        self.assertEqual(self.indent.procurement_type, Indent.ProcurementType.INTERNAL)

    def test_depadmin_approve_external_stock_sets_approved(self):
        self.indent.stock_available = False
        self.indent.procurement_type = Indent.ProcurementType.EXTERNAL
        self.indent.save(
            update_fields=["stock_available", "procurement_type", "updated_at"]
        )
        apply_hod_action(
            self.indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )
        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.APPROVED)
        self.assertEqual(self.indent.procurement_type, Indent.ProcurementType.EXTERNAL)

    def test_depadmin_direct_approve_routes_to_ps_admin(self):
        direct_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Direct approve to PS Admin",
            status=Indent.Status.FORWARDED,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=direct_indent, item=self.item1, quantity=2)

        apply_hod_action(
            direct_indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )

        direct_indent.refresh_from_db()
        self.assertEqual(direct_indent.status, Indent.Status.APPROVED)
        self.assertTrue(direct_indent.stock_available)
        self.assertEqual(direct_indent.procurement_type, Indent.ProcurementType.INTERNAL)
        self.assertIsNone(direct_indent.current_approver)

        ps_categories = get_ps_admin_indents_by_category(
            self._actor(ActingRole.PS_ADMIN, self.ps_admin_info)
        )
        self.assertIn(direct_indent.id, [indent["id"] for indent in ps_categories["pending"]])

    def test_depadmin_direct_approve_no_stock_marks_external(self):
        """Direct approval with no available stock should mark indent as EXTERNAL."""
        # Create an indent for an item with no stock
        item_no_stock = StoreItem.objects.create(name="Expensive Device", unit="nos")
        # Don't create any CurrentStock for this item
        
        direct_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Request device not in stock",
            status=Indent.Status.FORWARDED,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=direct_indent, item=item_no_stock, quantity=1)

        apply_hod_action(
            direct_indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )

        direct_indent.refresh_from_db()
        self.assertEqual(direct_indent.status, Indent.Status.APPROVED)
        self.assertFalse(direct_indent.stock_available)
        self.assertEqual(direct_indent.procurement_type, Indent.ProcurementType.EXTERNAL)

    def test_depadmin_allocate_stock_reduces_central_and_increases_department_stock(self):
        """ALLOCATE_STOCK should decrement central current stock and update department stock."""
        # Ensure indent is in a state where allocation is allowed
        self.indent.status = Indent.Status.STOCK_CHECKED
        self.indent.stock_available = True
        self.indent.procurement_type = Indent.ProcurementType.INTERNAL
        self.indent.save(update_fields=["status", "stock_available", "procurement_type", "updated_at"])

        apply_hod_action(
            self.indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "ALLOCATE_STOCK",
            notes="Allocating stock for request",
            request_user=self.depadmin_user,
        )

        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.STOCK_ALLOCATED)
        self.assertEqual(CurrentStock.objects.get(item=self.item1).quantity, 17)
        self.assertEqual(
            DepartmentStock.objects.get(stock_name="Pen", department="dep_cse").quantity,
            2,
        )

    def test_depadmin_allocate_stock_reduces_department_stock_when_dept_inventory_used(self):
        """ALLOCATE_STOCK should consume department stock when central stock is unavailable."""
        item_dept_only = StoreItem.objects.create(name="Notebook", unit="nos")
        DepartmentStock.objects.create(
            stock_name="Notebook",
            department="dep_cse",
            quantity=5,
        )

        dept_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Request from dept stock",
            status=Indent.Status.STOCK_CHECKED,
            stock_available=True,
            procurement_type=Indent.ProcurementType.INTERNAL,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=dept_indent, item=item_dept_only, quantity=2)

        apply_hod_action(
            dept_indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "ALLOCATE_STOCK",
            notes="Allocating department stock",
            request_user=self.depadmin_user,
        )

        self.assertEqual(
            DepartmentStock.objects.get(stock_name="Notebook", department="dep_cse").quantity,
            3,
        )
        self.assertEqual(CurrentStock.objects.filter(item=item_dept_only).count(), 0)

    def test_stock_breakdown_counts_department_stock_for_available_items(self):
        """Stock breakdown should show available when department stock satisfies the request."""
        item_laptop = StoreItem.objects.create(name="Laptop", unit="nos")
        DepartmentStock.objects.create(
            stock_name="laptop",
            department="dep_cse",
            quantity=2,
        )

        breakdown_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Laptop request",
            status=Indent.Status.FORWARDED,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=breakdown_indent, item=item_laptop, quantity=2)

        data = get_stock_breakdown_data(
            indent_id=breakdown_indent.id,
            actor=self._actor(ActingRole.DEPADMIN, self.depadmin_info),
        )

        self.assertTrue(data["all_available"])
        self.assertEqual(data["items"][0]["available_qty"], 2)
        self.assertTrue(data["items"][0]["ok"])

    def test_ps_admin_internal_allocate(self):
        apply_hod_action(
            self.indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )
        apply_ps_admin_action(
            self.indent.id,
            self._actor(ActingRole.PS_ADMIN, self.ps_admin_info),
            "INTERNAL_ALLOCATE",
            notes="",
            request_user=self.ps_admin_user,
        )
        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.INTERNAL_ISSUED)
        self.assertTrue(self.indent.delivery_confirmed)
        self.assertEqual(CurrentStock.objects.get(item=self.item1).quantity, 17)
        self.assertEqual(
            DepartmentStock.objects.get(stock_name="Pen", department="dep_cse").quantity,
            5,
        )

    def test_ps_admin_internal_allocate_from_dept_stock(self):
        """Allocation should succeed when item is in department stock, not central."""
        # Create an item with no central stock
        item_dept_only = StoreItem.objects.create(name="Notebook", unit="nos")
        # Add it to department stock only
        DepartmentStock.objects.create(
            stock_name="Notebook", department="dep_cse", quantity=5
        )
        
        # Create indent for this item (no central stock)
        dept_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Request from dept stock",
            status=Indent.Status.FORWARDED,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=dept_indent, item=item_dept_only, quantity=2)
        
        # DepAdmin approves - should recognize department stock
        apply_hod_action(
            dept_indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )
        
        dept_indent.refresh_from_db()
        self.assertEqual(dept_indent.status, Indent.Status.APPROVED)
        self.assertTrue(dept_indent.stock_available)
        self.assertEqual(dept_indent.procurement_type, Indent.ProcurementType.INTERNAL)
        
        # PS Admin allocates - should succeed using department stock
        apply_ps_admin_action(
            dept_indent.id,
            self._actor(ActingRole.PS_ADMIN, self.ps_admin_info),
            "INTERNAL_ALLOCATE",
            notes="",
            request_user=self.ps_admin_user,
        )
        
        dept_indent.refresh_from_db()
        self.assertEqual(dept_indent.status, Indent.Status.INTERNAL_ISSUED)
        self.assertTrue(dept_indent.delivery_confirmed)
        # Department stock should be decremented because the request consumes local inventory.
        self.assertEqual(
            DepartmentStock.objects.get(stock_name="Notebook", department="dep_cse").quantity,
            3,
        )

    def test_depadmin_approve_internal_when_department_stock_matches_laptop(self):
        """Laptop in department stock should be treated as internal procurement."""
        item_laptop = StoreItem.objects.create(name="Laptop", unit="nos")
        DepartmentStock.objects.create(
            stock_name="laptop",
            department="dep_cse",
            quantity=1,
        )

        direct_indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Laptop request",
            status=Indent.Status.FORWARDED,
            current_approver=self.depadmin_info,
        )
        IndentItem.objects.create(indent=direct_indent, item=item_laptop, quantity=1)

        apply_hod_action(
            direct_indent.id,
            self._actor(ActingRole.DEPADMIN, self.depadmin_info),
            "APPROVE",
            notes="",
            request_user=self.depadmin_user,
        )

        direct_indent.refresh_from_db()
        self.assertEqual(direct_indent.status, Indent.Status.APPROVED)
        self.assertTrue(direct_indent.stock_available)
        self.assertEqual(direct_indent.procurement_type, Indent.ProcurementType.INTERNAL)


class DirectorApprovalRoutingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.dept = DepartmentInfo.objects.create(code="CSE", name="Computer Science")
        self.director_designation = Designation.objects.create(name="Director")
        self.registrar_designation = Designation.objects.create(name="Registrar")

        self.director_user = User.objects.create_user(username="director", password="pass1234")
        self.registrar_user = User.objects.create_user(username="registrar", password="pass1234")
        self.employee_user = User.objects.create_user(username="employee", password="pass1234")

        self.director_info = ExtraInfo.objects.create(
            user=self.director_user, department=self.dept, employee_id="director"
        )
        self.registrar_info = ExtraInfo.objects.create(
            user=self.registrar_user, department=self.dept, employee_id="registrar"
        )
        self.employee_info = ExtraInfo.objects.create(
            user=self.employee_user, department=self.dept, employee_id="employee"
        )

        HoldsDesignation.objects.create(
            designation=self.director_designation,
            working=self.director_info,
            is_active=True,
        )
        HoldsDesignation.objects.create(
            designation=self.registrar_designation,
            working=self.registrar_info,
            is_active=True,
        )

        self.item1 = StoreItem.objects.create(name="Pen", unit="nos")
        self.indent = Indent.objects.create(
            indenter=self.employee_info,
            department=self.dept,
            purpose="Route through registrar",
            status=Indent.Status.FORWARDED_TO_DIRECTOR,
            current_approver=self.director_info,
        )
        IndentItem.objects.create(indent=self.indent, item=self.item1, quantity=2)

    def _actor(self, role, extrainfo):
        return SimpleNamespace(role=role, extrainfo=extrainfo)

    def test_director_approval_routes_to_registrar(self):
        apply_hod_action(
            self.indent.id,
            self._actor(ActingRole.DIRECTOR, self.director_info),
            "APPROVE",
            notes="",
            request_user=self.director_user,
        )

        self.indent.refresh_from_db()
        self.assertEqual(self.indent.status, Indent.Status.FORWARDED)
        self.assertEqual(self.indent.current_approver, self.registrar_info)
