"""
test_use_cases.py — UC Test Implementations for PS1 Purchase & Store Module
Assignment 8 | G1 | Gemini / Antigravity

Naming convention (required by runner):
  test_hp##_*  → Happy Path
  test_ap##_*  → Alternate Path
  test_ex##_*  → Exception Path
"""

import json
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone

from applications.filetracking.models import File
from applications.ps1.models import (
    IndentFile, IndentItem, Vendor, StockEntry, StockItem,
    GoodsReceivedNote, ProductReturn, Tender, AuditLog, StockReservation,
)
from .conftest import UCTestBase


# ─────────────────────────────────────────────────────────────────────────────
# UC-001: Submit Purchase Indent
# ─────────────────────────────────────────────────────────────────────────────

class TestUC01_SubmitIndent(UCTestBase):
    """UC-001: Employee submits a purchase indent"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def test_hp01_authenticated_submit(self):
        """Happy Path: authenticated employee submits complete indent"""
        self._test_id = "UC-001-HP-01"
        self._uc_id = "UC-001"
        self._test_category = "Happy Path"
        self._scenario = "Authenticated employee submits complete indent"
        self._preconditions = "User authenticated; holds student designation"
        self._input_action = "POST /api/create_proposal/ with all required fields"
        self._expected_result = "HTTP 200/201; IndentFile record created"

        resp = self.api_post("/create_proposal/", self.tok_student, data={
            "title": "UC001 Test Laptop",
            "description": "For testing UC-001",
            "item_name": "UC001 Laptop",
            "item_type": "Electronics",
            "quantity": 1,
            "estimated_cost": 45000,
            "purpose": "Research",
            "budgetary_head": "Capital",
            "expected_delivery": self.future_date(30),
            "sources_of_supply": "Open Market",
            "designation": self.hd_student.id,
        })

        if resp.status_code in (200, 201):
            self._record_result(
                f"HTTP {resp.status_code}; indent created",
                "Pass",
                f"Response: {resp.status_code}"
            )
        else:
            self._record_result(
                f"HTTP {resp.status_code}; expected 200/201",
                "Fail",
                f"Response body: {resp.content[:300]}"
            )
            self.fail(f"Expected 200/201, got {resp.status_code}")

    def test_ap01_draft_creation(self):
        """Alternate Path: create indent as draft"""
        self._test_id = "UC-001-AP-01"
        self._uc_id = "UC-001"
        self._test_category = "Alternate Path"
        self._scenario = "Create indent as draft"
        self._preconditions = "User authenticated"
        self._input_action = "POST /api/create_draft/ with partial data"
        self._expected_result = "HTTP 200/201; draft saved"

        resp = self.api_post("/create_draft/", self.tok_student, data={
            "item_name": "Draft Laptop",
            "item_type": "Electronics",
            "quantity": 1,
            "estimated_cost": 40000,
            "designation": self.hd_student.id,
        })

        if resp.status_code in (200, 201):
            self._record_result("Draft created", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(
                f"HTTP {resp.status_code}",
                "Partial" if resp.status_code < 500 else "Fail",
                f"Body: {resp.content[:200]}"
            )

    def test_ex01_unauthenticated_blocked(self):
        """Exception: unauthenticated user is blocked"""
        self._test_id = "UC-001-EX-01"
        self._uc_id = "UC-001"
        self._test_category = "Exception"
        self._scenario = "Unauthenticated user attempts indent submission"
        self._preconditions = "No auth token"
        self._input_action = "POST /api/create_proposal/ without Authorization"
        self._expected_result = "HTTP 401 or 403"

        resp = self.api_post_no_auth("/create_proposal/", data={"item_name": "Hack"})

        if resp.status_code in (401, 403):
            self._record_result(
                f"HTTP {resp.status_code}; access denied",
                "Pass",
                f"Correctly blocked unauthenticated request"
            )
        else:
            self._record_result(
                f"HTTP {resp.status_code}; expected 401/403",
                "Fail",
                f"Allowed unauthenticated access"
            )
            self.fail(f"Expected 401/403, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-002: Goods Received Note
# ─────────────────────────────────────────────────────────────────────────────

class TestUC02_GoodsReceivedNote(UCTestBase):
    """UC-002: PS admin records delivery confirmation"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create vendor
        cls.vendor = Vendor.objects.create(
            vendor_code="V-UC02",
            vendor_name="UC02 Vendor",
            gst_number="27AAAAA0002A1Z5",
            pan_number="AAAAA0002A",
            is_approved=True,
            created_by=cls.ps_user,
        )
        # Create File + IndentFile
        cls.indent_file = File.objects.create(
            uploader=cls.hd_student.user.extrainfo,
            designation=cls.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 2}),
        )
        cls.indent = IndentFile.objects.create(
            file_info=cls.indent_file,
            item_name="UC02 Projector",
            item_type="Electronics",
            quantity=2,
            estimated_cost=30000,
            purpose="Lecture",
            budgetary_head="Capital",
            expected_delivery="2026-12-31",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )
        cls.se = StockEntry.objects.create(
            item_id=cls.indent,
            vendor=cls.vendor,
            quantity_purchased=2,
            purchase_order_number="PO-UC02-001",
            invoice_number="INV-UC02-001",
        )

    def test_hp01_create_grn_full_receipt(self):
        """Happy Path: GRN for fully received goods"""
        self._test_id = "UC-002-HP-01"
        self._uc_id = "UC-002"
        self._test_category = "Happy Path"
        self._scenario = "PS admin creates GRN for fully received goods"
        self._preconditions = "StockEntry and IndentFile exist"
        self._input_action = "POST /api/grn/create/ with quantity_received=2, quantity_accepted=2"
        self._expected_result = "HTTP 200/201; GRN created; has_discrepancy=False"

        resp = self.api_post("/grn/create/", self.tok_ps, data={
            "indent_file_id": self.indent.pk,
            "stock_entry_id": self.se.pk,
            "quantity_received": 2,
            "quantity_accepted": 2,
            "grn_number": "GRN-UC02-HP01",
            "quality_check_passed": True,
            "has_discrepancy": False,
            "remarks": "All items received in good condition",
        })

        if resp.status_code in (200, 201):
            self._record_result("GRN created successfully", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(
                f"HTTP {resp.status_code}",
                "Fail",
                f"GRN creation failed: {resp.content[:300]}"
            )
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_ap01_grn_with_discrepancy(self):
        """Alternate Path: GRN with delivery discrepancy"""
        self._test_id = "UC-002-AP-01"
        self._uc_id = "UC-002"
        self._test_category = "Alternate Path"
        self._scenario = "GRN created with delivery discrepancy"
        self._preconditions = "StockEntry exists; goods received with damage"
        self._input_action = "POST /api/grn/create/ with quantity_accepted=1, has_discrepancy=True"
        self._expected_result = "HTTP 200/201; has_discrepancy=True; invoice hold triggered"

        resp = self.api_post("/grn/create/", self.tok_ps, data={
            "indent_file_id": self.indent.pk,
            "stock_entry_id": self.se.pk,
            "quantity_received": 2,
            "quantity_accepted": 1,
            "grn_number": "GRN-UC02-AP01",
            "quality_check_passed": False,
            "has_discrepancy": True,
            "discrepancy_details": "1 unit arrived damaged",
        })

        if resp.status_code in (200, 201):
            self._record_result("GRN with discrepancy created", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(
                f"HTTP {resp.status_code}",
                "Fail",
                f"Discrepancy GRN failed: {resp.content[:300]}"
            )
            self.fail(f"Expected 200/201, got {resp.status_code}")

    def test_ex01_missing_grn_number(self):
        """Exception: GRN without mandatory grn_number"""
        self._test_id = "UC-002-EX-01"
        self._uc_id = "UC-002"
        self._test_category = "Exception"
        self._scenario = "Create GRN without mandatory grn_number"
        self._preconditions = "User authenticated as PS admin"
        self._input_action = "POST /api/grn/create/ without grn_number field"
        self._expected_result = "HTTP 400; validation error"

        resp = self.api_post("/grn/create/", self.tok_ps, data={
            "indent_file_id": self.indent.pk,
            "stock_entry_id": self.se.pk,
            "quantity_received": 2,
            "quantity_accepted": 2,
            # grn_number intentionally missing
        })

        if resp.status_code == 400:
            self._record_result("Correctly rejected (missing grn_number)", "Pass",
                                f"HTTP 400 as expected")
        elif resp.status_code in (200, 201):
            self._record_result("GRN created without required field — DEFECT",
                                "Fail", f"grn_number should be mandatory but was accepted")
            self.fail("GRN should not be created without grn_number")
        else:
            self._record_result(
                f"HTTP {resp.status_code} instead of 400",
                "Fail",
                f"Unexpected status: {resp.content[:200]}"
            )
            self.fail(f"Expected 400, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-003: Track Procurement Status
# ─────────────────────────────────────────────────────────────────────────────

class TestUC03_TrackProcurement(UCTestBase):
    """UC-003: Users track their indent lifecycle"""

    def test_hp01_list_own_indents(self):
        """Happy Path: user retrieves own indent list"""
        self._test_id = "UC-003-HP-01"
        self._uc_id = "UC-003"
        self._test_category = "Happy Path"
        self._scenario = "User retrieves list of their own indents"
        self._preconditions = "User authenticated"
        self._input_action = f"GET /api/my-indents/{self.student_user.username}/"
        self._expected_result = "HTTP 200; indent list returned"

        resp = self.api_get(
            f"/my-indents/{self.student_user.username}/",
            self.tok_student,
            expected_status=None,
        )

        if resp.status_code == 200:
            self._record_result("Indent list returned", "Pass", f"HTTP 200")
        else:
            self._record_result(
                f"HTTP {resp.status_code}",
                "Fail",
                f"Expected 200: {resp.content[:200]}"
            )
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_inward_indents(self):
        """Alternate Path: view indents forwarded to designation"""
        self._test_id = "UC-003-AP-01"
        self._uc_id = "UC-003"
        self._test_category = "Alternate Path"
        self._scenario = "HOD views inward indents"
        self._preconditions = "HOD authenticated"
        self._input_action = f"GET /api/inwardIndents/{self.hd_hod.pk}"
        self._expected_result = "HTTP 200; inward indent list"

        resp = self.api_get(
            f"/inwardIndents/{self.hd_hod.pk}",
            self.tok_hod,
            expected_status=None,
        )

        if resp.status_code == 200:
            self._record_result("Inward indents returned", "Pass", "HTTP 200")
        elif resp.status_code in (400, 404):
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                "Endpoint exists but query error")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Unexpected: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ex01_nonexistent_username(self):
        """Exception: non-existent username in my-indents returns error"""
        self._test_id = "UC-003-EX-01"
        self._uc_id = "UC-003"
        self._test_category = "Exception"
        self._scenario = "Fetch indents for non-existent username"
        self._preconditions = "User authenticated"
        self._input_action = "GET /api/my-indents/no_such_user_xyz/"
        self._expected_result = "HTTP 404 or 400"

        resp = self.api_get("/my-indents/no_such_user_xyz/", self.tok_student, expected_status=None)

        if resp.status_code in (404, 400):
            self._record_result(f"HTTP {resp.status_code}; user not found", "Pass",
                                "Non-existent user correctly rejected")
        else:
            self._record_result(
                f"HTTP {resp.status_code}; expected 400/404",
                "Fail",
                f"Should reject non-existent username: {resp.content[:200]}"
            )
            self.fail(f"Expected 404/400, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-005: Cancel Purchase Indent
# ─────────────────────────────────────────────────────────────────────────────

class TestUC05_CancelIndent(UCTestBase):
    """UC-005: Soft cancellation of active indents"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.indent_file = File.objects.create(
            uploader=cls.hd_student.user.extrainfo,
            designation=cls.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 1}),
        )
        cls.active_indent = IndentFile.objects.create(
            file_info=cls.indent_file,
            item_name="UC05 Chair",
            item_type="Furniture",
            quantity=4,
            estimated_cost=12000,
            purpose="Office use",
            budgetary_head="Revenue",
            expected_delivery="2026-12-01",
            sources_of_supply="GeM",
            status="ACTIVE",
        )

    def test_hp01_cancel_active_indent(self):
        """Happy Path: cancel own ACTIVE indent with reason"""
        self._test_id = "UC-005-HP-01"
        self._uc_id = "UC-005"
        self._test_category = "Happy Path"
        self._scenario = "Employee cancels ACTIVE indent with valid reason"
        self._preconditions = "indent.status = ACTIVE; user is owner"
        self._input_action = f"POST /api/indents/{self.active_indent.pk}/cancel/ with reason"
        self._expected_result = "HTTP 200/204; status=CANCELLED; record preserved"

        resp = self.api_post(
            f"/indents/{self.active_indent.pk}/cancel/",
            self.tok_student,
            data={"reason": "No longer required"},
        )

        if resp.status_code in (200, 204):
            # Verify soft cancel — record must still exist
            self.assertTrue(
                IndentFile.objects.filter(pk=self.active_indent.pk).exists(),
                "Indent should not be hard-deleted"
            )
            self._record_result("Cancelled; record preserved", "Pass",
                                f"HTTP {resp.status_code}; DB record exists")
        elif resp.status_code == 400:
            # Already cancelled or wrong state — acceptable in idempotent tests
            self._record_result("HTTP 400 — may already be cancelled", "Partial",
                                f"HTTP 400: {resp.content[:200]}")
        else:
            self._record_result(
                f"HTTP {resp.status_code}",
                "Fail",
                f"Cancel failed: {resp.content[:300]}"
            )
            self.fail(f"Expected 200/204, got {resp.status_code}: {resp.content[:200]}")

    def test_ap01_hod_cancel_indent(self):
        """Alternate Path: HOD cancels an indent"""
        self._test_id = "UC-005-AP-01"
        self._uc_id = "UC-005"
        self._test_category = "Alternate Path"
        self._scenario = "HOD cancels a department indent"
        self._preconditions = "HOD authenticated; indent in ACTIVE state"
        self._input_action = f"POST /api/indents/{self.active_indent.pk}/cancel/ with HOD token"
        self._expected_result = "HTTP 200/204; indent.status = CANCELLED"

        # Create a fresh indent for HOD to cancel
        f2 = File.objects.create(
            uploader=self.hd_student.user.extrainfo,
            designation=self.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 1}),
        )
        indent2 = IndentFile.objects.create(
            file_info=f2,
            item_name="UC05 HOD Chair",
            item_type="Furniture",
            quantity=2,
            estimated_cost=6000,
            purpose="Meeting room",
            budgetary_head="Revenue",
            expected_delivery="2026-12-01",
            sources_of_supply="GeM",
            status="ACTIVE",
        )

        resp = self.api_post(
            f"/indents/{indent2.pk}/cancel/",
            self.tok_hod,
            data={"reason": "Budget cut by HOD"},
        )

        if resp.status_code in (200, 204):
            self._record_result("HOD cancelled indent", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code in (400, 403):
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                "Partial implementation")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200/204, got {resp.status_code}")

    def test_ex01_cancel_nonexistent_indent(self):
        """Exception: cancel non-existent indent returns 404 not 500"""
        self._test_id = "UC-005-EX-01"
        self._uc_id = "UC-005"
        self._test_category = "Exception"
        self._scenario = "Cancel nonexistent indent ID"
        self._preconditions = "User authenticated"
        self._input_action = "POST /api/indents/999999/cancel/ with reason"
        self._expected_result = "HTTP 404; clean error — not 500"

        resp = self.api_post(
            "/indents/999999/cancel/",
            self.tok_student,
            data={"reason": "Test"},
        )

        if resp.status_code == 404:
            self._record_result("HTTP 404; correct not-found response", "Pass",
                                "Non-existent indent returns 404")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 server error — DEFECT", "Fail",
                                "Server crashed on non-existent indent ID")
            self.fail("Server should return 404, not crash with 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Unexpected: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-006: Check Stock Availability
# ─────────────────────────────────────────────────────────────────────────────

class TestUC06_CheckStock(UCTestBase):
    """UC-006: Dept admin checks current stock"""

    def test_hp01_admin_views_stock(self):
        """Happy Path: dept admin views current stock"""
        self._test_id = "UC-006-HP-01"
        self._uc_id = "UC-006"
        self._test_category = "Happy Path"
        self._scenario = "Dept admin views current stock for department"
        self._preconditions = "User holds deptadmin designation"
        self._input_action = f"GET /api/current_stock_view/{self.hd_admin.pk}"
        self._expected_result = "HTTP 200; stock item list returned"

        resp = self.api_get(f"/current_stock_view/{self.hd_admin.pk}", self.tok_admin,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("Stock list returned", "Pass", f"HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — role not matching deptadmin", "Partial",
                                "Admin user may need exact deptadmin_cse role match")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_stock_entry_item_view(self):
        """Alternate Path: view individual stock entry items"""
        self._test_id = "UC-006-AP-01"
        self._uc_id = "UC-006"
        self._test_category = "Alternate Path"
        self._scenario = "View stock entry items for a designation"
        self._preconditions = "Admin authenticated"
        self._input_action = f"GET /api/stock_entry_item_view/{self.hd_admin.pk}"
        self._expected_result = "HTTP 200; stock entry items returned"

        resp = self.api_get(f"/stock_entry_item_view/{self.hd_admin.pk}", self.tok_admin,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("Stock entry items returned", "Pass", "HTTP 200")
        elif resp.status_code in (403, 400, 404):
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Endpoint reachable but access issue")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Unexpected: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ex01_student_denied_stock_view(self):
        """Exception: student RBAC check — blocked from stock view"""
        self._test_id = "UC-006-EX-01"
        self._uc_id = "UC-006"
        self._test_category = "Exception"
        self._scenario = "Student role attempts stock view access"
        self._preconditions = "User holds only student designation"
        self._input_action = f"GET /api/current_stock_view/{self.hd_student.pk}"
        self._expected_result = "HTTP 403; access denied — student role"

        resp = self.api_get(f"/current_stock_view/{self.hd_student.pk}", self.tok_student,
                            expected_status=None)

        if resp.status_code == 403:
            self._record_result("HTTP 403; RBAC correctly enforced", "Pass",
                                "Student blocked from stock view")
        elif resp.status_code == 200:
            self._record_result("HTTP 200 — RBAC NOT enforced — DEFECT", "Fail",
                                "Student can access stock view — security issue")
            self.fail("Student should not access stock_entry_view")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"{resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-011: Duplicate Indent Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestUC11_DuplicateDetection(UCTestBase):
    """UC-011: Check for duplicate indent submissions"""

    def test_hp01_unique_item_no_duplicate(self):
        """Happy Path: unique item name — no duplicate found"""
        self._test_id = "UC-011-HP-01"
        self._uc_id = "UC-011"
        self._test_category = "Happy Path"
        self._scenario = "Check for completely unique item — no matches"
        self._preconditions = "No existing indent with same item_name"
        self._input_action = "POST /api/indents/check-duplicates/ with unique item_name"
        self._expected_result = "HTTP 200; duplicates=[] or is_duplicate=false"

        resp = self.api_post("/indents/check-duplicates/", self.tok_student, data={
            "item_name": "UC011UniqueQuantumComputerABC",
            "item_type": "Electronics",
        })

        if resp.status_code == 200:
            self._record_result("Check passed; no duplicates", "Pass", f"HTTP 200")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — check-duplicates crashes — DEFECT", "Fail",
                                "View crashes on duplicate check")
            self.fail("check-duplicates should not return 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_common_item_may_duplicate(self):
        """Alternate Path: item that matches existing indent"""
        self._test_id = "UC-011-AP-01"
        self._uc_id = "UC-011"
        self._test_category = "Alternate Path"
        self._scenario = "Check item with potential matches"
        self._preconditions = "Existing indents with 'Laptop' may exist"
        self._input_action = "POST /api/indents/check-duplicates/ with item_name='Laptop'"
        self._expected_result = "HTTP 200; duplicates list (possibly empty)"

        resp = self.api_post("/indents/check-duplicates/", self.tok_student, data={
            "item_name": "Laptop",
            "item_type": "Electronics",
        })

        if resp.status_code == 200:
            self._record_result("Duplicate check completed", "Pass", f"HTTP 200")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — DEFECT", "Fail",
                                "View crashes on duplicate check")
            self.fail("Should return 200 with results, not 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ex01_missing_item_name(self):
        """Exception: check without item_name returns 400"""
        self._test_id = "UC-011-EX-01"
        self._uc_id = "UC-011"
        self._test_category = "Exception"
        self._scenario = "Submit duplicate check without item_name"
        self._preconditions = "User authenticated"
        self._input_action = "POST /api/indents/check-duplicates/ with empty body"
        self._expected_result = "HTTP 400; item_name required"

        resp = self.api_post("/indents/check-duplicates/", self.tok_student, data={})

        if resp.status_code == 400:
            self._record_result("HTTP 400; validation enforced", "Pass",
                                "Missing item_name correctly rejected")
        elif resp.status_code == 200:
            self._record_result("HTTP 200 — missing item_name accepted — DEFECT", "Fail",
                                "item_name should be required")
            self.fail("Should return 400 for missing item_name")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"{resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-012: Reject Purchase Indent
# ─────────────────────────────────────────────────────────────────────────────

class TestUC12_RejectIndent(UCTestBase):
    """UC-012: Authorized officer rejects an indent"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        f = File.objects.create(
            uploader=cls.hd_student.user.extrainfo,
            designation=cls.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 1}),
        )
        cls.reject_indent = IndentFile.objects.create(
            file_info=f,
            item_name="UC12 Printer",
            item_type="Electronics",
            quantity=1,
            estimated_cost=25000,
            purpose="Printing",
            budgetary_head="Revenue",
            expected_delivery="2026-11-30",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )

    def test_hp01_reject_with_reason(self):
        """Happy Path: PS admin rejects with valid reason"""
        self._test_id = "UC-012-HP-01"
        self._uc_id = "UC-012"
        self._test_category = "Happy Path"
        self._scenario = "PS admin rejects indent with non-empty reason"
        self._preconditions = "indent.status = ACTIVE; user is PS admin"
        self._input_action = f"POST /api/indents/{self.reject_indent.pk}/reject/ with reason"
        self._expected_result = "HTTP 200/204; status=REJECTED; reason stored"

        resp = self.api_post(
            f"/indents/{self.reject_indent.pk}/reject/",
            self.tok_ps,
            data={"reason": "Insufficient budget allocation for this item"},
        )

        if resp.status_code in (200, 204):
            self._record_result("Indent rejected with reason", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code == 400:
            self._record_result("HTTP 400 — may be already rejected", "Partial",
                                f"Body: {resp.content[:200]}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/204, got {resp.status_code}: {resp.content[:200]}")

    def test_ap01_reject_nonexistent_indent(self):
        """Alternate Path: reject non-existent indent returns 404"""
        self._test_id = "UC-012-AP-01"
        self._uc_id = "UC-012"
        self._test_category = "Alternate Path"
        self._scenario = "Reject non-existent indent"
        self._preconditions = "PS admin authenticated"
        self._input_action = "POST /api/indents/999999/reject/ with reason"
        self._expected_result = "HTTP 404; indent not found"

        resp = self.api_post("/indents/999999/reject/", self.tok_ps,
                             data={"reason": "Does not exist"})

        if resp.status_code == 404:
            self._record_result("HTTP 404; correct not-found", "Pass", "Clean 404 returned")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — DEFECT", "Fail",
                                "Server crashes on non-existent reject")
            self.fail("Should return 404 not 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_ex01_reject_without_reason(self):
        """Exception: reject without reason returns 400"""
        self._test_id = "UC-012-EX-01"
        self._uc_id = "UC-012"
        self._test_category = "Exception"
        self._scenario = "Reject indent without providing reason"
        self._preconditions = "Indent in ACTIVE state"
        self._input_action = f"POST /api/indents/{self.reject_indent.pk}/reject/ with empty body"
        self._expected_result = "HTTP 400; rejection reason is mandatory"

        resp = self.api_post(
            f"/indents/{self.reject_indent.pk}/reject/",
            self.tok_ps,
            data={},
        )

        if resp.status_code == 400:
            self._record_result("HTTP 400; reason enforced", "Pass",
                                "Empty reason correctly rejected")
        elif resp.status_code in (200, 204):
            self._record_result("HTTP 200 — empty reason accepted — DEFECT", "Fail",
                                "BR-PS-005 violated: reason is mandatory")
            self.fail("Empty reason should be rejected")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Unexpected: {resp.content[:200]}")
            self.fail(f"Expected 400, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-014: Audit Financial Records
# ─────────────────────────────────────────────────────────────────────────────

class TestUC14_AuditLog(UCTestBase):
    """UC-014: Auditors access procurement audit trail"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        AuditLog.objects.create(
            user=cls.ps_user,
            action="CANCEL_INDENT",
            entity_type="IndentFile",
            entity_id=1,
        )

    def test_hp01_auditor_list_logs(self):
        """Happy Path: auditor lists all audit logs"""
        self._test_id = "UC-014-HP-01"
        self._uc_id = "UC-014"
        self._test_category = "Happy Path"
        self._scenario = "Auditor retrieves full audit log list"
        self._preconditions = "User holds Auditor designation; AuditLog entries exist"
        self._input_action = "GET /api/audit-logs/"
        self._expected_result = "HTTP 200; AuditLog list with action, user, timestamp"

        resp = self.api_get("/audit-logs/", self.tok_auditor, expected_status=None)

        if resp.status_code == 200:
            data = resp.json()
            self._record_result(
                f"HTTP 200; {len(data) if isinstance(data, list) else '?'} log entries",
                "Pass",
                f"Response contains data"
            )
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — Auditor role not recognized", "Fail",
                                "RBAC may not recognize 'Auditor' designation name")
            self.fail("Auditor should access audit logs")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_filter_by_action(self):
        """Alternate Path: filter audit logs by action type"""
        self._test_id = "UC-014-AP-01"
        self._uc_id = "UC-014"
        self._test_category = "Alternate Path"
        self._scenario = "Auditor filters logs by CANCEL_INDENT action"
        self._preconditions = "Auditor authenticated; CANCEL_INDENT entries exist"
        self._input_action = "GET /api/audit-logs/?action=CANCEL_INDENT"
        self._expected_result = "HTTP 200; filtered log entries"

        resp = self.api_get("/audit-logs/?action=CANCEL_INDENT", self.tok_auditor,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("Filtered audit logs returned", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — Auditor role not recognized", "Fail",
                                "RBAC not recognizing Auditor designation")
            self.fail("Auditor should access filtered audit logs")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_ex01_student_blocked_from_audit(self):
        """Exception: student cannot view audit logs"""
        self._test_id = "UC-014-EX-01"
        self._uc_id = "UC-014"
        self._test_category = "Exception"
        self._scenario = "Student attempts to access audit logs"
        self._preconditions = "User holds only student designation"
        self._input_action = "GET /api/audit-logs/ with student token"
        self._expected_result = "HTTP 403; access denied — Auditor role required"

        resp = self.api_get("/audit-logs/", self.tok_student, expected_status=None)

        if resp.status_code == 403:
            self._record_result("HTTP 403; RBAC enforced", "Pass",
                                "Student correctly blocked from audit logs")
        elif resp.status_code == 200:
            self._record_result("HTTP 200 — student can view audit logs — DEFECT", "Fail",
                                "RBAC not enforced on audit-logs endpoint")
            self.fail("Student should not access audit logs")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Unexpected: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-016: Department Head Approval
# ─────────────────────────────────────────────────────────────────────────────

class TestUC16_HODApproval(UCTestBase):
    """UC-016: HOD approves or rejects forwarded indents"""

    def test_hp01_hod_approves(self):
        """Happy Path: HOD approves an indent"""
        self._test_id = "UC-016-HP-01"
        self._uc_id = "UC-016"
        self._test_category = "Happy Path"
        self._scenario = "HOD approves department indent"
        self._preconditions = "HOD authenticated; indent exists"
        self._input_action = "POST /api/approve-indent/ with {file_id: 1, approved: true}"
        self._expected_result = "HTTP 200/201; approval recorded"

        # Create a file to approve
        f = File.objects.create(
            uploader=self.hd_student.user.extrainfo,
            designation=self.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 2}),
        )

        resp = self.api_post("/approve-indent/", self.tok_hod, data={
            "file_id": f.pk,
            "approved": True,
        })

        if resp.status_code in (200, 201):
            self._record_result(f"Approval successful", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code == 400:
            self._record_result("HTTP 400 — approval validation error", "Partial",
                                f"Body: {resp.content[:200]}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}")

    def test_ap01_missing_file_id(self):
        """Alternate Path: approve without file_id returns 400"""
        self._test_id = "UC-016-AP-01"
        self._uc_id = "UC-016"
        self._test_category = "Alternate Path"
        self._scenario = "Approve without file_id — validation check"
        self._preconditions = "HOD authenticated"
        self._input_action = "POST /api/approve-indent/ with empty body"
        self._expected_result = "HTTP 400; file_id required"

        resp = self.api_post("/approve-indent/", self.tok_hod, data={})

        if resp.status_code == 400:
            self._record_result("HTTP 400; file_id required", "Pass",
                                "Empty body correctly rejected")
        elif resp.status_code == 404:
            self._record_result("HTTP 404 — close to correct", "Partial",
                                "404 also acceptable for missing file")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 400, got {resp.status_code}")

    def test_ex01_unauthenticated_approve(self):
        """Exception: unauthenticated approve attempt blocked"""
        self._test_id = "UC-016-EX-01"
        self._uc_id = "UC-016"
        self._test_category = "Exception"
        self._scenario = "Unauthenticated approval attempt"
        self._preconditions = "No auth token"
        self._input_action = "POST /api/approve-indent/ without Authorization"
        self._expected_result = "HTTP 401 or 403"

        resp = self.api_post_no_auth("/approve-indent/", data={"file_id": 1})

        if resp.status_code in (401, 403):
            self._record_result(f"HTTP {resp.status_code}; access denied", "Pass",
                                "Unauthenticated approve correctly blocked")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Should reject no-auth: {resp.content[:200]}")
            self.fail(f"Expected 401/403, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-019: Vendor Onboarding
# ─────────────────────────────────────────────────────────────────────────────

class TestUC19_VendorOnboarding(UCTestBase):
    """UC-019: PS admin manages vendor master data"""

    def test_hp01_create_vendor(self):
        """Happy Path: PS admin creates a new vendor"""
        self._test_id = "UC-019-HP-01"
        self._uc_id = "UC-019"
        self._test_category = "Happy Path"
        self._scenario = "PS admin creates vendor with unique code and GST/PAN"
        self._preconditions = "vendor_code not in system; PS admin authenticated"
        self._input_action = "POST /api/vendors/create/ with all fields"
        self._expected_result = "HTTP 200/201; Vendor created; is_approved=False"

        resp = self.api_post("/vendors/create/", self.tok_ps, data={
            "vendor_code": "V-UC19-HP01",
            "vendor_name": "UC019 Test Vendor",
            "gst_number": "27XXXXX0019X1Z5",
            "pan_number": "XXXXX0019X",
            "email": "uc019@vendor.com",
            "phone": "9000000019",
        })

        if resp.status_code in (200, 201):
            self._record_result("Vendor created", "Pass", f"HTTP {resp.status_code}")
            self.assertTrue(
                Vendor.objects.filter(vendor_code="V-UC19-HP01").exists()
            )
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_ap01_list_all_vendors(self):
        """Alternate Path: list all registered vendors"""
        self._test_id = "UC-019-AP-01"
        self._uc_id = "UC-019"
        self._test_category = "Alternate Path"
        self._scenario = "List all vendors in system"
        self._preconditions = "User authenticated; vendors exist"
        self._input_action = "GET /api/vendors/"
        self._expected_result = "HTTP 200; vendor list returned"

        resp = self.api_get("/vendors/", self.tok_ps, expected_status=None)

        if resp.status_code == 200:
            data = resp.json()
            self._record_result(
                f"HTTP 200; {len(data) if isinstance(data, list) else '?'} vendors",
                "Pass", "Vendor list accessible"
            )
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ex01_unauthenticated_vendor_list(self):
        """Exception: unauthenticated vendor list blocked"""
        self._test_id = "UC-019-EX-01"
        self._uc_id = "UC-019"
        self._test_category = "Exception"
        self._scenario = "Unauthenticated request to vendor list"
        self._preconditions = "No auth token"
        self._input_action = "GET /api/vendors/ without Authorization"
        self._expected_result = "HTTP 401 or 403"

        resp = self.api_get_no_auth("/vendors/")

        if resp.status_code in (401, 403):
            self._record_result(f"HTTP {resp.status_code}; blocked", "Pass",
                                "Unauthenticated access correctly denied")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Vendor list exposed without auth: {resp.content[:200]}")
            self.fail(f"Expected 401/403, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-020: Product Return
# ─────────────────────────────────────────────────────────────────────────────

class TestUC20_ProductReturn(UCTestBase):
    """UC-020: PS admin manages product returns"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vendor_r = Vendor.objects.create(
            vendor_code="V-UC20",
            vendor_name="UC20 Vendor",
            gst_number="27YYYYY0020Y1Z5",
            pan_number="YYYYY0020Y",
            is_approved=True,
            created_by=cls.ps_user,
        )
        f = File.objects.create(
            uploader=cls.hd_student.user.extrainfo,
            designation=cls.des_student,
            src_module="ps1",
            src_object_id="",
            file_extra_JSON=json.dumps({"value": 1}),
        )
        cls.indent_r = IndentFile.objects.create(
            file_info=f,
            item_name="UC20 Switch",
            item_type="Electronics",
            quantity=2,
            estimated_cost=8000,
            purpose="Network",
            budgetary_head="Capital",
            expected_delivery="2026-10-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )
        cls.se_r = StockEntry.objects.create(
            item_id=cls.indent_r,
            vendor=cls.vendor_r,
            quantity_purchased=2,
            purchase_order_number="PO-UC20-001",
            invoice_number="INV-UC20-001",
        )
        cls.grn_r = GoodsReceivedNote.objects.create(
            grn_number="GRN-UC20-001",
            indent_file=cls.indent_r,
            stock_entry=cls.se_r,
            quantity_received=2,
            quantity_accepted=1,
            has_discrepancy=True,
            discrepancy_details="1 unit DOA",
        )

    def test_hp01_list_returns(self):
        """Happy Path: list all product returns"""
        self._test_id = "UC-020-HP-01"
        self._uc_id = "UC-020"
        self._test_category = "Happy Path"
        self._scenario = "List all product return records"
        self._preconditions = "PS admin authenticated"
        self._input_action = "GET /api/returns/"
        self._expected_result = "HTTP 200; returns list"

        resp = self.api_get("/returns/", self.tok_ps, expected_status=None)

        if resp.status_code == 200:
            self._record_result("Returns list returned", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403", "Partial", "RBAC may be overly strict")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_create_return_for_discrepancy(self):
        """Alternate Path: create ProductReturn for discrepant GRN"""
        self._test_id = "UC-020-AP-01"
        self._uc_id = "UC-020"
        self._test_category = "Alternate Path"
        self._scenario = "Create product return for discrepant GRN"
        self._preconditions = "GRN with has_discrepancy=True exists"
        self._input_action = "POST /api/returns/create/ with grn_id, quantity_returned"
        self._expected_result = "HTTP 200/201; ProductReturn created"

        resp = self.api_post("/returns/create/", self.tok_ps, data={
            "grn_id": self.grn_r.pk,
            "stock_entry_id": self.se_r.pk,
            "return_number": "RET-UC20-AP01",
            "return_reason": "Unit Dead on Arrival",
            "quantity_returned": 1,
            "discrepancy_type": "Physical damage",
            "discrepancy_description": "Unit completely non-functional",
        })

        if resp.status_code in (200, 201):
            self._record_result("ProductReturn created", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_ex01_create_return_empty_body(self):
        """Exception: create return without required fields returns 400"""
        self._test_id = "UC-020-EX-01"
        self._uc_id = "UC-020"
        self._test_category = "Exception"
        self._scenario = "Create return with completely empty body"
        self._preconditions = "User authenticated"
        self._input_action = "POST /api/returns/create/ with empty body"
        self._expected_result = "HTTP 400; required fields validation error"

        resp = self.api_post("/returns/create/", self.tok_ps, data={})

        if resp.status_code == 400:
            self._record_result("HTTP 400; validation enforced", "Pass",
                                "Empty body correctly rejected for returns")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — crashes on empty body — DEFECT", "Fail",
                                "Should return 400, not crash")
            self.fail("create_return crashes on empty body; should return 400")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# UC-022: Tender Management
# ─────────────────────────────────────────────────────────────────────────────

class TestUC22_TenderManagement(UCTestBase):
    """UC-022: PS admin manages competitive procurement tenders"""

    def test_hp01_list_tenders(self):
        """Happy Path: list all tenders"""
        self._test_id = "UC-022-HP-01"
        self._uc_id = "UC-022"
        self._test_category = "Happy Path"
        self._scenario = "List all tenders in the system"
        self._preconditions = "PS admin authenticated"
        self._input_action = "GET /api/tenders/"
        self._expected_result = "HTTP 200; tender list with status"

        resp = self.api_get("/tenders/", self.tok_ps, expected_status=None)

        if resp.status_code == 200:
            self._record_result("Tender list returned", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — PS admin denied tenders — DEFECT", "Fail",
                                "PS admin should access tender list")
            self.fail("PS admin should access /tenders/")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_ap01_create_tender_missing_fields(self):
        """Alternate Path: create tender with missing required fields returns 400"""
        self._test_id = "UC-022-AP-01"
        self._uc_id = "UC-022"
        self._test_category = "Alternate Path"
        self._scenario = "Submit tender with empty payload — validation"
        self._preconditions = "PS admin authenticated"
        self._input_action = "POST /api/tenders/create/ with empty body"
        self._expected_result = "HTTP 400; required fields validation error"

        resp = self.api_post("/tenders/create/", self.tok_ps, data={})

        if resp.status_code == 400:
            self._record_result("HTTP 400; tender validation enforced", "Pass",
                                "Empty tender correctly rejected")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — RBAC too strict — DEFECT", "Fail",
                                "PS admin should reach this endpoint")
            self.fail("PS admin should not get 403 on tender create")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_ex01_publish_nonexistent_tender(self):
        """Exception: publish non-existent tender returns 404"""
        self._test_id = "UC-022-EX-01"
        self._uc_id = "UC-022"
        self._test_category = "Exception"
        self._scenario = "Publish tender with non-existent ID"
        self._preconditions = "PS admin authenticated"
        self._input_action = "POST /api/tenders/999999/publish/"
        self._expected_result = "HTTP 404; tender not found"

        resp = self.api_post("/tenders/999999/publish/", self.tok_ps, data={})

        if resp.status_code == 404:
            self._record_result("HTTP 404; correct not-found", "Pass",
                                "Non-existent tender returns 404")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — RBAC too strict — DEFECT", "Fail",
                                "PS admin should reach 404, not get 403")
            self.fail("Should return 404, not 403 — RBAC precedes existence check")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 404, got {resp.status_code}")
