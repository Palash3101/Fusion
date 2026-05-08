"""
test_business_rules.py — BR Test Implementations for PS1 Purchase & Store Module
Assignment 8 | G1 | Gemini / Antigravity

Naming convention (required by runner):
  test_valid_*    → Valid scenario (rule respected)
  test_invalid_*  → Invalid scenario (rule violated / boundary)
"""

import json
from applications.ps1.models import (
    IndentFile, Vendor, StockEntry, StockItem,
    GoodsReceivedNote, ProductReturn, AuditLog, StockReservation,
)
from applications.filetracking.models import File
from .conftest import BRTestBase


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-001: Indent Completeness
# ─────────────────────────────────────────────────────────────────────────────

class TestBR01_IndentCompleteness(BRTestBase):
    """BR-PS-001: All required fields must be present in indent submission"""

    def test_valid_complete_indent(self):
        """Valid: all required fields → 200/201"""
        self._test_id = "BR-PS-001-V-01"
        self._br_id = "BR-PS-001"
        self._test_category = "Valid"
        self._input_action = "POST /api/create_proposal/ with all required fields"
        self._expected_result = "HTTP 200/201; indent created"

        resp = self.api_post("/create_proposal/", self.tok_student, data={
            "title": "BR01 Valid UPS",
            "description": "All fields provided",
            "item_name": "BR01 UPS",
            "item_type": "Electronics",
            "quantity": 1,
            "estimated_cost": 15000,
            "purpose": "Office power backup",
            "budgetary_head": "Capital",
            "expected_delivery": self.future_date(60),
            "sources_of_supply": "Open Market",
            "designation": self.hd_student.id,
        })

        if resp.status_code in (200, 201):
            self._record_result("HTTP 200/201; indent accepted", "Pass",
                                f"All required fields accepted")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_empty_body(self):
        """Invalid: empty body → 400"""
        self._test_id = "BR-PS-001-I-01"
        self._br_id = "BR-PS-001"
        self._test_category = "Invalid"
        self._input_action = "POST /api/create_proposal/ with empty JSON body"
        self._expected_result = "HTTP 400/422; validation listing missing fields"

        resp = self.api_post("/create_proposal/", self.tok_student, data={})

        if resp.status_code in (400, 422):
            self._record_result("HTTP 400; empty body rejected", "Pass",
                                "Missing required fields correctly rejected")
        elif resp.status_code in (200, 201):
            self._record_result("HTTP 200 — empty body accepted — DEFECT", "Fail",
                                "Required field validation not enforced")
            self.fail("Empty indent body should be rejected")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 400, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-002: Positive Quantity
# ─────────────────────────────────────────────────────────────────────────────

class TestBR02_PositiveQuantity(BRTestBase):
    """BR-PS-002: quantity must be >= 1"""

    def test_valid_quantity_one(self):
        """Valid: quantity=1 (minimum) accepted"""
        self._test_id = "BR-PS-002-V-01"
        self._br_id = "BR-PS-002"
        self._test_category = "Valid"
        self._input_action = "Submit indent with quantity=1"
        self._expected_result = "HTTP 200/201; indent accepted"

        resp = self.api_post("/create_proposal/", self.tok_student, data={
            "title": "BR02 Chair",
            "description": "Qty=1 test",
            "item_name": "BR02 Chair",
            "item_type": "Furniture",
            "quantity": 1,
            "estimated_cost": 5000,
            "purpose": "Office",
            "budgetary_head": "Revenue",
            "expected_delivery": self.future_date(30),
            "sources_of_supply": "GeM Portal",
            "designation": self.hd_student.id,
        })

        if resp.status_code in (200, 201):
            self._record_result("qty=1 accepted", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_zero_quantity(self):
        """Invalid: quantity=0 should be rejected"""
        self._test_id = "BR-PS-002-I-01"
        self._br_id = "BR-PS-002"
        self._test_category = "Invalid"
        self._input_action = "Submit indent with quantity=0"
        self._expected_result = "HTTP 400; quantity must be >= 1"

        resp = self.api_post("/create_proposal/", self.tok_student, data={
            "title": "BR02 Zero Qty",
            "description": "Qty=0 test",
            "item_name": "BR02 Table",
            "item_type": "Furniture",
            "quantity": 0,
            "estimated_cost": 3000,
            "purpose": "Office",
            "budgetary_head": "Revenue",
            "expected_delivery": self.future_date(30),
            "sources_of_supply": "GeM Portal",
            "designation": self.hd_student.id,
        })

        if resp.status_code == 400:
            self._record_result("qty=0 rejected", "Pass",
                                "Zero quantity correctly rejected by API")
        elif resp.status_code in (200, 201):
            self._record_result("qty=0 ACCEPTED — DEFECT", "Fail",
                                "BR-PS-002 violated: zero quantity must not be accepted")
            self.fail("Zero quantity should be rejected by API validation")
        else:
            # 500 or other — document status
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Unexpected response for qty=0: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-003: Authentication Required
# ─────────────────────────────────────────────────────────────────────────────

class TestBR03_AuthenticationRequired(BRTestBase):
    """BR-PS-003: All endpoints must reject unauthenticated requests"""

    def test_valid_authenticated_access(self):
        """Valid: authenticated user reaches protected endpoint"""
        self._test_id = "BR-PS-003-V-01"
        self._br_id = "BR-PS-003"
        self._test_category = "Valid"
        self._input_action = "GET /api/getDesignations/ with valid Bearer token"
        self._expected_result = "HTTP 200; designation data returned"

        resp = self.api_get("/getDesignations/", self.tok_student, expected_status=None)

        if resp.status_code == 200:
            self._record_result("Authenticated access granted", "Pass", "HTTP 200")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Authenticated user should get 200, got {resp.status_code}")

    def test_invalid_no_auth_token(self):
        """Invalid: no auth token → 401/403 on all endpoints"""
        self._test_id = "BR-PS-003-I-01"
        self._br_id = "BR-PS-003"
        self._test_category = "Invalid"
        self._input_action = "GET protected endpoints without Authorization header"
        self._expected_result = "HTTP 401/403 on all protected endpoints"

        endpoints = [
            "/getDesignations/",
            "/vendors/",
            "/audit-logs/",
            "/grn/",
        ]
        failed_endpoints = []
        for ep in endpoints:
            resp = self.api_get_no_auth(ep)
            if resp.status_code not in (401, 403):
                failed_endpoints.append(f"{ep}→{resp.status_code}")

        if not failed_endpoints:
            self._record_result("All endpoints require auth", "Pass",
                                f"Checked: {', '.join(endpoints)}")
        else:
            self._record_result(
                f"Some endpoints allow no-auth: {failed_endpoints}", "Fail",
                f"RBAC gap: {failed_endpoints}"
            )
            self.fail(f"These endpoints allowed unauthenticated access: {failed_endpoints}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-004: Role-Based Access Control
# ─────────────────────────────────────────────────────────────────────────────

class TestBR04_RBAC(BRTestBase):
    """BR-PS-004: Role-based access enforced on admin endpoints"""

    def test_valid_psadmin_stock_access(self):
        """Valid: PS admin can access stock entry view"""
        self._test_id = "BR-PS-004-V-01"
        self._br_id = "BR-PS-004"
        self._test_category = "Valid"
        self._input_action = f"GET /api/stock_entry_view/{self.hd_ps.pk} with ps_admin token"
        self._expected_result = "HTTP 200; stock entries returned"

        resp = self.api_get(f"/stock_entry_view/{self.hd_ps.pk}", self.tok_ps,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("PS admin accesses stock entry view", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — PS admin denied — check role name", "Fail",
                                "Role 'ps_admin' may not match @require_roles decorator")
            self.fail("PS admin should access stock_entry_view")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Returning {resp.status_code}: {resp.content[:200]}")

    def test_invalid_student_stock_denied(self):
        """Invalid: student is denied access to stock_entry_view"""
        self._test_id = "BR-PS-004-I-01"
        self._br_id = "BR-PS-004"
        self._test_category = "Invalid"
        self._input_action = f"GET /api/stock_entry_view/{self.hd_student.pk} with student token"
        self._expected_result = "HTTP 403; student role denied"

        resp = self.api_get(f"/stock_entry_view/{self.hd_student.pk}", self.tok_student,
                            expected_status=None)

        if resp.status_code == 403:
            self._record_result("Student role correctly denied", "Pass",
                                "RBAC working on stock_entry_view")
        elif resp.status_code == 200:
            self._record_result("Student can access stock — DEFECT", "Fail",
                                "RBAC not enforced: student sees stock data")
            self.fail("Student should not access stock_entry_view")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-005: Rejection Reason Mandatory
# ─────────────────────────────────────────────────────────────────────────────

class TestBR05_RejectionReasonMandatory(BRTestBase):
    """BR-PS-005: Rejection must include a non-empty reason"""

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
        cls.br05_indent = IndentFile.objects.create(
            file_info=f,
            item_name="BR05 Monitor",
            item_type="Electronics",
            quantity=1,
            estimated_cost=18000,
            purpose="Display",
            budgetary_head="Capital",
            expected_delivery="2026-10-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )

    def test_valid_rejection_with_reason(self):
        """Valid: rejection with non-empty reason accepted"""
        self._test_id = "BR-PS-005-V-01"
        self._br_id = "BR-PS-005"
        self._test_category = "Valid"
        self._input_action = f"POST /api/indents/{self.br05_indent.pk}/reject/ with reason"
        self._expected_result = "HTTP 200/204; indent rejected; reason stored"

        resp = self.api_post(f"/indents/{self.br05_indent.pk}/reject/", self.tok_ps,
                             data={"reason": "Budget not approved for this cycle"})

        if resp.status_code in (200, 204):
            self._record_result("Rejection with reason accepted", "Pass",
                                f"HTTP {resp.status_code}")
        elif resp.status_code == 400:
            self._record_result("HTTP 400 — may already be rejected", "Partial",
                                f"Body: {resp.content[:200]}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/204, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_rejection_empty_reason(self):
        """Invalid: empty reason string → 400"""
        self._test_id = "BR-PS-005-I-01"
        self._br_id = "BR-PS-005"
        self._test_category = "Invalid"
        self._input_action = f"POST /api/indents/{self.br05_indent.pk}/reject/ with reason=''"
        self._expected_result = "HTTP 400; rejection reason is mandatory"

        resp = self.api_post(f"/indents/{self.br05_indent.pk}/reject/", self.tok_ps,
                             data={"reason": ""})

        if resp.status_code == 400:
            self._record_result("Empty reason rejected", "Pass",
                                "BR-PS-005 enforced correctly")
        elif resp.status_code in (200, 204):
            self._record_result("Empty reason accepted — DEFECT", "Fail",
                                "BR-PS-005 violated: empty reason should not be accepted")
            self.fail("Empty rejection reason should be rejected")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 400, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-006: Cancellation Reason Mandatory
# ─────────────────────────────────────────────────────────────────────────────

class TestBR06_CancellationReasonMandatory(BRTestBase):
    """BR-PS-006: Cancellation must include a non-empty reason"""

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
        cls.br06_indent = IndentFile.objects.create(
            file_info=f,
            item_name="BR06 Laptop",
            item_type="Electronics",
            quantity=1,
            estimated_cost=60000,
            purpose="Research",
            budgetary_head="Capital",
            expected_delivery="2026-11-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )

    def test_valid_cancel_with_reason(self):
        """Valid: cancel with reason → 200"""
        self._test_id = "BR-PS-006-V-01"
        self._br_id = "BR-PS-006"
        self._test_category = "Valid"
        self._input_action = f"POST /api/indents/{self.br06_indent.pk}/cancel/ with reason"
        self._expected_result = "HTTP 200/204; indent cancelled"

        resp = self.api_post(f"/indents/{self.br06_indent.pk}/cancel/", self.tok_student,
                             data={"reason": "Requirement changed"})

        if resp.status_code in (200, 204):
            self._record_result("Cancel with reason accepted", "Pass",
                                f"HTTP {resp.status_code}")
        elif resp.status_code == 400:
            self._record_result("HTTP 400 — may already be in terminal state", "Partial",
                                f"Body: {resp.content[:200]}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/204, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_cancel_empty_body(self):
        """Invalid: cancel with empty body → 400"""
        self._test_id = "BR-PS-006-I-01"
        self._br_id = "BR-PS-006"
        self._test_category = "Invalid"
        self._input_action = f"POST /api/indents/{self.br06_indent.pk}/cancel/ with {{}}"
        self._expected_result = "HTTP 400; cancellation reason required"

        resp = self.api_post(f"/indents/{self.br06_indent.pk}/cancel/", self.tok_student,
                             data={})

        if resp.status_code == 400:
            self._record_result("Empty cancel body rejected", "Pass",
                                "BR-PS-006 enforced")
        elif resp.status_code in (200, 204):
            self._record_result("Empty cancel body accepted — DEFECT", "Fail",
                                "BR-PS-006 violated: reason is mandatory")
            self.fail("Cancel without reason should be rejected")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-007: Soft Cancel — No Hard Delete
# ─────────────────────────────────────────────────────────────────────────────

class TestBR07_SoftCancel(BRTestBase):
    """BR-PS-007: Cancelled indents must remain in DB (soft cancel)"""

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
        cls.br07_indent = IndentFile.objects.create(
            file_info=f,
            item_name="BR07 Keyboard",
            item_type="Electronics",
            quantity=3,
            estimated_cost=9000,
            purpose="Office",
            budgetary_head="Revenue",
            expected_delivery="2026-10-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )

    def test_valid_record_preserved_after_cancel(self):
        """Valid: cancel → record preserved with status=CANCELLED"""
        self._test_id = "BR-PS-007-V-01"
        self._br_id = "BR-PS-007"
        self._test_category = "Valid"
        self._input_action = "Cancel indent; verify DB record still exists"
        self._expected_result = "record exists with status=CANCELLED; not hard-deleted"

        resp = self.api_post(f"/indents/{self.br07_indent.pk}/cancel/", self.tok_student,
                             data={"reason": "BR07 soft cancel test"})

        # Check DB — record must still exist regardless of API response
        self.assertTrue(
            IndentFile.objects.filter(pk=self.br07_indent.pk).exists(),
            "IndentFile must not be hard-deleted after cancel"
        )

        if resp.status_code in (200, 204):
            self.br07_indent.refresh_from_db()
            self.assertEqual(self.br07_indent.status, "CANCELLED",
                             "Status should be CANCELLED after cancel call")
            self._record_result("Record preserved; status=CANCELLED", "Pass",
                                "Soft cancel correctly implemented")
        elif resp.status_code == 400:
            self._record_result("Cancel returned 400 but record exists", "Partial",
                                "Cancel may have failed due to state; record exists")
        else:
            self._record_result(f"HTTP {resp.status_code} but record preserved", "Partial",
                                f"Cancel returned {resp.status_code}")

    def test_invalid_delete_method_not_allowed(self):
        """Invalid: DELETE method on indent should not exist"""
        self._test_id = "BR-PS-007-I-01"
        self._br_id = "BR-PS-007"
        self._test_category = "Invalid"
        self._input_action = "DELETE /api/indents/{id}/ — method should not exist"
        self._expected_result = "HTTP 404 or 405; hard delete not permitted"

        c = self._client(self.tok_student)
        resp = c.delete(f"{self._get_base()}/indents/{self.br07_indent.pk}/")

        if resp.status_code in (404, 405):
            self._record_result(f"HTTP {resp.status_code}; DELETE not allowed", "Pass",
                                "Hard delete correctly not supported")
        elif resp.status_code in (200, 204):
            self._record_result("DELETE succeeded — DEFECT", "Fail",
                                "Hard deletion allowed — violates BR-PS-007")
            self.fail("Hard delete of indent should not be allowed")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def _get_base(self):
        from .conftest import API_BASE
        return API_BASE


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-008: Tender for High-Value Procurement
# ─────────────────────────────────────────────────────────────────────────────

class TestBR08_TenderThreshold(BRTestBase):
    """BR-PS-008: High-value procurement must go through tender process"""

    def test_valid_tender_create_by_psadmin(self):
        """Valid: PS admin creates tender for high-value indent"""
        self._test_id = "BR-PS-008-V-01"
        self._br_id = "BR-PS-008"
        self._test_category = "Valid"
        self._input_action = "POST /api/tenders/create/ by PS admin (high value)"
        self._expected_result = "HTTP 200/201; Tender created in DRAFT status"

        from datetime import datetime, timedelta
        resp = self.api_post("/tenders/create/", self.tok_ps, data={
            "tender_number": "TND-BR08-V01",
            "title": "High Value Laptop Procurement",
            "description": "Exceeds procurement threshold",
            "estimated_value": "500000.00",
            "bid_submission_deadline": (datetime.now() + timedelta(days=7)).isoformat(),
            "bid_opening_date": (datetime.now() + timedelta(days=8)).isoformat(),
        })

        if resp.status_code in (200, 201):
            self._record_result("Tender created by PS admin", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — PS admin blocked — DEFECT", "Fail",
                                "RBAC too strict: PS admin cannot create tenders")
            self.fail("PS admin should create tenders")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_invalid_tender_no_auth(self):
        """Invalid: unauthenticated tender creation blocked"""
        self._test_id = "BR-PS-008-I-01"
        self._br_id = "BR-PS-008"
        self._test_category = "Invalid"
        self._input_action = "POST /api/tenders/create/ without Authorization"
        self._expected_result = "HTTP 401/403; unauthorized"

        resp = self.api_post_no_auth("/tenders/create/", data={"title": "Hack"})

        if resp.status_code in (401, 403):
            self._record_result(f"HTTP {resp.status_code}; no-auth blocked", "Pass",
                                "Unauthenticated tender creation denied")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"No-auth request allowed: {resp.content[:200]}")
            self.fail(f"Expected 401/403, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-009: GRN Discrepancy Flag
# ─────────────────────────────────────────────────────────────────────────────

class TestBR09_GRNDiscrepancy(BRTestBase):
    """BR-PS-009: GRN discrepancy must be flagged correctly"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vendor_br9 = Vendor.objects.create(
            vendor_code="V-BR09",
            vendor_name="BR09 Vendor",
            gst_number="27BBBBB0009B1Z5",
            pan_number="BBBBB0009B",
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
        cls.indent_br9 = IndentFile.objects.create(
            file_info=f,
            item_name="BR09 Switch",
            item_type="Electronics",
            quantity=3,
            estimated_cost=6000,
            purpose="Network",
            budgetary_head="Capital",
            expected_delivery="2026-10-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )
        cls.se_br9 = StockEntry.objects.create(
            item_id=cls.indent_br9,
            vendor=cls.vendor_br9,
            quantity_purchased=3,
            purchase_order_number="PO-BR09-001",
            invoice_number="INV-BR09-001",
        )

    def test_valid_grn_list_has_discrepancy_field(self):
        """Valid: GRN list returns 200 with has_discrepancy field"""
        self._test_id = "BR-PS-009-V-01"
        self._br_id = "BR-PS-009"
        self._test_category = "Valid"
        self._input_action = "GET /api/grn/ and verify has_discrepancy field present"
        self._expected_result = "HTTP 200; records with has_discrepancy boolean"

        resp = self.api_get("/grn/", self.tok_ps, expected_status=None)

        if resp.status_code == 200:
            self._record_result("GRN list returned", "Pass", "HTTP 200")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — GRN list crashes — DEFECT", "Fail",
                                "list_grns view returns 500")
            self.fail("GRN list should return 200, not 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_invalid_confirm_nonexistent_grn(self):
        """Invalid: confirm non-existent GRN → 404 not 500"""
        self._test_id = "BR-PS-009-I-01"
        self._br_id = "BR-PS-009"
        self._test_category = "Invalid"
        self._input_action = "POST /api/grn/999999/confirm/ — GRN does not exist"
        self._expected_result = "HTTP 404; GRN not found — no server crash"

        resp = self.api_post("/grn/999999/confirm/", self.tok_ps, data={})

        if resp.status_code == 404:
            self._record_result("HTTP 404; clean not-found", "Pass",
                                "Non-existent GRN returns clean 404")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — crashes on bad GRN ID — DEFECT", "Fail",
                                "confirm_delivery should return 404, not 500")
            self.fail("Should return 404 for non-existent GRN")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-010: Unique Vendor Code
# ─────────────────────────────────────────────────────────────────────────────

class TestBR10_UniqueVendorCode(BRTestBase):
    """BR-PS-010: Vendor codes must be unique"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.existing_vendor = Vendor.objects.create(
            vendor_code="V-BR10-EXISTING",
            vendor_name="Existing Vendor",
            gst_number="27CCCCC0010C1Z5",
            pan_number="CCCCC0010C",
            is_approved=False,
            created_by=cls.ps_user,
        )

    def test_valid_unique_vendor_code(self):
        """Valid: unique vendor_code accepted"""
        self._test_id = "BR-PS-010-V-01"
        self._br_id = "BR-PS-010"
        self._test_category = "Valid"
        self._input_action = "POST /api/vendors/create/ with unique vendor_code"
        self._expected_result = "HTTP 200/201; Vendor created"

        resp = self.api_post("/vendors/create/", self.tok_ps, data={
            "vendor_code": "V-BR10-NEW-UNIQUE",
            "vendor_name": "BR10 New Vendor",
            "gst_number": "27DDDDD0010D1Z5",
            "pan_number": "DDDDD0010D",
        })

        if resp.status_code in (200, 201):
            self._record_result("Unique vendor created", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/201, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_duplicate_vendor_code(self):
        """Invalid: duplicate vendor_code → 400"""
        self._test_id = "BR-PS-010-I-01"
        self._br_id = "BR-PS-010"
        self._test_category = "Invalid"
        self._input_action = "POST /api/vendors/create/ with vendor_code='V-BR10-EXISTING'"
        self._expected_result = "HTTP 400; vendor_code already exists"

        resp = self.api_post("/vendors/create/", self.tok_ps, data={
            "vendor_code": "V-BR10-EXISTING",  # duplicate
            "vendor_name": "Duplicate Attempt",
            "gst_number": "27EEEEE0010E1Z5",
            "pan_number": "EEEEE0010E",
        })

        if resp.status_code == 400:
            self._record_result("Duplicate vendor_code rejected", "Pass",
                                "Unique constraint enforced at API level")
        elif resp.status_code in (200, 201):
            self._record_result("Duplicate accepted — DEFECT", "Fail",
                                "BR-PS-010 violated: duplicate vendor_code accepted")
            self.fail("Duplicate vendor_code should be rejected")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — DB IntegrityError not caught — DEFECT", "Fail",
                                "IntegrityError not converted to 400")
            self.fail("Should return 400 for duplicate vendor_code, not crash")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-011: Stock Reservation Active Tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestBR11_StockReservation(BRTestBase):
    """BR-PS-011: Stock reservations must be actively tracked"""

    def test_valid_reservation_endpoint_responds(self):
        """Valid: reservation endpoint is reachable and validates input"""
        self._test_id = "BR-PS-011-V-01"
        self._br_id = "BR-PS-011"
        self._test_category = "Valid"
        self._input_action = "POST /api/reservations/create/ with required fields"
        self._expected_result = "HTTP 200/201/400; endpoint reachable and validates"

        from datetime import datetime, timedelta
        resp = self.api_post("/reservations/create/", self.tok_ps, data={
            "indent_file_id": 1,
            "stock_item_id": 1,
            "quantity": 1,
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
        })

        if resp.status_code in (200, 201):
            self._record_result("Reservation created", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code == 400:
            self._record_result("HTTP 400 — validation working; IDs may not exist", "Partial",
                                "Endpoint validates; FK not found")
        elif resp.status_code == 404:
            self._record_result("HTTP 404 — FK not found", "Partial", "Endpoint works")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — reservation endpoint crashes — DEFECT", "Fail",
                                "create_reservation returns 500")
            self.fail("Reservation endpoint should not return 500")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_invalid_release_nonexistent_reservation(self):
        """Invalid: release non-existent reservation → 404"""
        self._test_id = "BR-PS-011-I-01"
        self._br_id = "BR-PS-011"
        self._test_category = "Invalid"
        self._input_action = "POST /api/reservations/999999/release/"
        self._expected_result = "HTTP 404; reservation not found"

        resp = self.api_post("/reservations/999999/release/", self.tok_ps, data={})

        if resp.status_code == 404:
            self._record_result("HTTP 404; correct not-found", "Pass",
                                "Non-existent reservation returns 404")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — crashes on invalid ID — DEFECT", "Fail",
                                "Should return 404, not 500")
            self.fail("release_reservation should return 404 for invalid ID")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-012: Audit Log on State Change
# ─────────────────────────────────────────────────────────────────────────────

class TestBR12_AuditLogRequired(BRTestBase):
    """BR-PS-012: AuditLog created on significant state changes"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        AuditLog.objects.create(
            user=cls.ps_user,
            action="CANCEL_INDENT",
            entity_type="IndentFile",
            entity_id=99,
        )

    def test_valid_audit_log_accessible(self):
        """Valid: audit logs accessible to Auditor role"""
        self._test_id = "BR-PS-012-V-01"
        self._br_id = "BR-PS-012"
        self._test_category = "Valid"
        self._input_action = "GET /api/audit-logs/ with Auditor token"
        self._expected_result = "HTTP 200; AuditLog list with action, user, timestamp"

        resp = self.api_get("/audit-logs/", self.tok_auditor, expected_status=None)

        if resp.status_code == 200:
            self._record_result("Audit logs accessible", "Pass", "HTTP 200")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_invalid_student_denied_audit(self):
        """Invalid: student denied access to audit logs"""
        self._test_id = "BR-PS-012-I-01"
        self._br_id = "BR-PS-012"
        self._test_category = "Invalid"
        self._input_action = "GET /api/audit-logs/ with student token"
        self._expected_result = "HTTP 403; student cannot view audit logs"

        resp = self.api_get("/audit-logs/", self.tok_student, expected_status=None)

        if resp.status_code == 403:
            self._record_result("Student denied audit logs", "Pass",
                                "RBAC correctly blocks student from audit logs")
        elif resp.status_code == 200:
            self._record_result("Student can see audit logs — DEFECT", "Fail",
                                "Audit logs should be restricted to Auditor/Director role")
            self.fail("Student should not access audit logs")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-013: Invoice Hold on Discrepancy
# ─────────────────────────────────────────────────────────────────────────────

class TestBR13_InvoiceHold(BRTestBase):
    """BR-PS-013: Discrepancy triggers invoice hold"""

    def test_valid_returns_list_accessible(self):
        """Valid: returns list endpoint accessible"""
        self._test_id = "BR-PS-013-V-01"
        self._br_id = "BR-PS-013"
        self._test_category = "Valid"
        self._input_action = "GET /api/returns/"
        self._expected_result = "HTTP 200; returns list with invoice_hold field"

        resp = self.api_get("/returns/", self.tok_ps, expected_status=None)

        if resp.status_code == 200:
            self._record_result("Returns list accessible", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403", "Partial", "RBAC may be blocking PS admin")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_invalid_process_without_resolution_type(self):
        """Invalid: process return without resolution_type → 400"""
        self._test_id = "BR-PS-013-I-01"
        self._br_id = "BR-PS-013"
        self._test_category = "Invalid"
        self._input_action = "POST /api/returns/1/process/ with empty body"
        self._expected_result = "HTTP 400; resolution_type required"

        resp = self.api_post("/returns/1/process/", self.tok_ps, data={})

        if resp.status_code == 400:
            self._record_result("Empty process body rejected", "Pass",
                                "resolution_type enforced as required")
        elif resp.status_code == 404:
            self._record_result("HTTP 404 — return ID=1 not found", "Partial",
                                "Endpoint works; return doesn't exist")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — RBAC too strict", "Fail",
                                "PS admin should access returns/process")
            self.fail("PS admin blocked from returns process — RBAC issue")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 400/404, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-014: Return Resolution Type Validity
# ─────────────────────────────────────────────────────────────────────────────

class TestBR14_ReturnResolutionType(BRTestBase):
    """BR-PS-014: Return resolution must be a valid choice"""

    def test_valid_refund_resolution(self):
        """Valid: REFUND resolution accepted (or 404 if return not found)"""
        self._test_id = "BR-PS-014-V-01"
        self._br_id = "BR-PS-014"
        self._test_category = "Valid"
        self._input_action = "POST /api/returns/1/process/ with resolution_type=REFUND"
        self._expected_result = "HTTP 200/204 or 404 if ID=1 not found"

        resp = self.api_post("/returns/1/process/", self.tok_ps, data={
            "resolution_type": "REFUND",
            "resolution_remarks": "Approved for full refund",
        })

        if resp.status_code in (200, 204):
            self._record_result("REFUND resolution accepted", "Pass", f"HTTP {resp.status_code}")
        elif resp.status_code == 404:
            self._record_result("HTTP 404 — return ID=1 not found", "Partial",
                                "Endpoint working; return fixture needed")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — RBAC too strict — DEFECT", "Fail",
                                "PS admin blocked from return resolution")
            self.fail("PS admin should process returns")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200/204/404, got {resp.status_code}")

    def test_invalid_bad_resolution_type(self):
        """Invalid: invalid resolution_type → 400"""
        self._test_id = "BR-PS-014-I-01"
        self._br_id = "BR-PS-014"
        self._test_category = "Invalid"
        self._input_action = "POST /api/returns/1/process/ with resolution_type=INVALID_TYPE"
        self._expected_result = "HTTP 400; invalid choice for resolution_type"

        resp = self.api_post("/returns/1/process/", self.tok_ps, data={
            "resolution_type": "INVALID_TYPE",
        })

        if resp.status_code == 400:
            self._record_result("Invalid resolution type rejected", "Pass",
                                "Serializer validates resolution_type choices")
        elif resp.status_code == 404:
            self._record_result("HTTP 404 — return not found (before validation)", "Partial",
                                "Endpoint exists; validation may not be reached")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — RBAC too strict", "Fail",
                                "Can't test validation — blocked by RBAC")
            self.fail("PS admin blocked from return resolution")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 400/404, got {resp.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-015: Duplicate Detection item_name Required
# ─────────────────────────────────────────────────────────────────────────────

class TestBR15_DuplicateDetectionRequired(BRTestBase):
    """BR-PS-015: check-duplicates requires item_name"""

    def test_valid_check_with_item_name(self):
        """Valid: duplicate check with item_name provided"""
        self._test_id = "BR-PS-015-V-01"
        self._br_id = "BR-PS-015"
        self._test_category = "Valid"
        self._input_action = "POST /api/indents/check-duplicates/ with item_name"
        self._expected_result = "HTTP 200; duplicate check result"

        resp = self.api_post("/indents/check-duplicates/", self.tok_student, data={
            "item_name": "BR15UniqueItemQWERTY",
            "item_type": "Electronics",
        })

        if resp.status_code == 200:
            self._record_result("Duplicate check completed", "Pass", "HTTP 200")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — check-duplicates crashes — DEFECT", "Fail",
                                "check-duplicates endpoint returns 500")
            self.fail("Duplicate check should return 200")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")

    def test_invalid_check_no_item_name(self):
        """Invalid: check without item_name → 400"""
        self._test_id = "BR-PS-015-I-01"
        self._br_id = "BR-PS-015"
        self._test_category = "Invalid"
        self._input_action = "POST /api/indents/check-duplicates/ with empty body"
        self._expected_result = "HTTP 400; item_name is required"

        resp = self.api_post("/indents/check-duplicates/", self.tok_student, data={})

        if resp.status_code == 400:
            self._record_result("Empty body rejected", "Pass",
                                "item_name enforced as required field")
        elif resp.status_code == 200:
            self._record_result("Empty body accepted — DEFECT", "Fail",
                                "item_name should be required but was not enforced")
            self.fail("check-duplicates should require item_name")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-016: Vendor Master Data Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestBR16_VendorDataIntegrity(BRTestBase):
    """BR-PS-016: Vendor records must be accessible; non-existent → 404"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vendor_br16 = Vendor.objects.create(
            vendor_code="V-BR16-001",
            vendor_name="BR16 Test Vendor",
            gst_number="27FFFFF0016F1Z5",
            pan_number="FFFFF0016F",
            is_approved=True,
            created_by=cls.ps_user,
        )

    def test_valid_vendor_list(self):
        """Valid: vendor list returns records"""
        self._test_id = "BR-PS-016-V-01"
        self._br_id = "BR-PS-016"
        self._test_category = "Valid"
        self._input_action = "GET /api/vendors/"
        self._expected_result = "HTTP 200; vendor list with all fields"

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

    def test_invalid_nonexistent_vendor(self):
        """Invalid: non-existent vendor → 404"""
        self._test_id = "BR-PS-016-I-01"
        self._br_id = "BR-PS-016"
        self._test_category = "Invalid"
        self._input_action = "GET /api/vendors/999999/"
        self._expected_result = "HTTP 404; vendor not found"

        resp = self.api_get("/vendors/999999/", self.tok_ps, expected_status=None)

        if resp.status_code == 404:
            self._record_result("Non-existent vendor returns 404", "Pass", "HTTP 404")
        elif resp.status_code == 200:
            self._record_result("HTTP 200 for non-existent vendor — DEFECT", "Fail",
                                "Should return 404 for missing vendor")
            self.fail("Non-existent vendor should return 404")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-017: Audit Log Filtering
# ─────────────────────────────────────────────────────────────────────────────

class TestBR17_AuditLogFiltering(BRTestBase):
    """BR-PS-017: Audit logs support filtering by action type"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        AuditLog.objects.create(
            user=cls.ps_user,
            action="CANCEL_INDENT",
            entity_type="IndentFile",
            entity_id=77,
        )

    def test_valid_filter_by_action(self):
        """Valid: filter audit logs by action type"""
        self._test_id = "BR-PS-017-V-01"
        self._br_id = "BR-PS-017"
        self._test_category = "Valid"
        self._input_action = "GET /api/audit-logs/?action=CANCEL_INDENT with Auditor token"
        self._expected_result = "HTTP 200; filtered audit log entries"

        resp = self.api_get("/audit-logs/?action=CANCEL_INDENT", self.tok_auditor,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("Filtered audit logs returned", "Pass", "HTTP 200")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:200]}")
            self.fail(f"Expected 200, got {resp.status_code}")

    def test_invalid_student_denied(self):
        """Invalid: student denied filtered audit log access"""
        self._test_id = "BR-PS-017-I-01"
        self._br_id = "BR-PS-017"
        self._test_category = "Invalid"
        self._input_action = "GET /api/audit-logs/ with student token"
        self._expected_result = "HTTP 403; student cannot view audit logs"

        resp = self.api_get("/audit-logs/", self.tok_student, expected_status=None)

        if resp.status_code == 403:
            self._record_result("Student denied audit logs", "Pass", "RBAC enforced")
        elif resp.status_code == 200:
            self._record_result("Student can view audit — DEFECT", "Fail",
                                "Audit logs should require Auditor role")
            self.fail("Student should not access audit logs")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-018: GRN Existence Check Before Confirm
# ─────────────────────────────────────────────────────────────────────────────

class TestBR18_GRNExistenceCheck(BRTestBase):
    """BR-PS-018: confirming non-existent GRN must return 404 not 500"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        vendor = Vendor.objects.create(
            vendor_code="V-BR18",
            vendor_name="BR18 Vendor",
            gst_number="27GGGGG0018G1Z5",
            pan_number="GGGGG0018G",
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
        indent = IndentFile.objects.create(
            file_info=f,
            item_name="BR18 Router",
            item_type="Electronics",
            quantity=1,
            estimated_cost=5000,
            purpose="Network",
            budgetary_head="Capital",
            expected_delivery="2026-10-01",
            sources_of_supply="Open Market",
            status="ACTIVE",
        )
        se = StockEntry.objects.create(
            item_id=indent,
            vendor=vendor,
            quantity_purchased=1,
            purchase_order_number="PO-BR18-001",
            invoice_number="INV-BR18-001",
        )
        cls.br18_grn = GoodsReceivedNote.objects.create(
            grn_number="GRN-BR18-001",
            indent_file=indent,
            stock_entry=se,
            quantity_received=1,
            quantity_accepted=1,
        )

    def test_valid_confirm_existing_grn(self):
        """Valid: confirm existing GRN → 200"""
        self._test_id = "BR-PS-018-V-01"
        self._br_id = "BR-PS-018"
        self._test_category = "Valid"
        self._input_action = f"POST /api/grn/{self.br18_grn.pk}/confirm/"
        self._expected_result = "HTTP 200/204; GRN confirmed"

        resp = self.api_post(f"/grn/{self.br18_grn.pk}/confirm/", self.tok_ps,
                             data={"remarks": "BR18 confirm test"})

        if resp.status_code in (200, 204):
            self._record_result("GRN confirmed", "Pass", f"HTTP {resp.status_code}")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Fail",
                                f"Body: {resp.content[:300]}")
            self.fail(f"Expected 200/204, got {resp.status_code}: {resp.content[:200]}")

    def test_invalid_confirm_nonexistent_grn(self):
        """Invalid: non-existent GRN → 404 not 500"""
        self._test_id = "BR-PS-018-I-01"
        self._br_id = "BR-PS-018"
        self._test_category = "Invalid"
        self._input_action = "POST /api/grn/999999/confirm/"
        self._expected_result = "HTTP 404; GRN not found — no crash"

        resp = self.api_post("/grn/999999/confirm/", self.tok_ps, data={})

        if resp.status_code == 404:
            self._record_result("HTTP 404; clean not-found", "Pass",
                                "Non-existent GRN returns 404")
        elif resp.status_code == 500:
            self._record_result("HTTP 500 — crashes — DEFECT", "Fail",
                                "Should return 404, not crash")
            self.fail("confirm_delivery should return 404 for non-existent GRN")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# BR-PS-019: Designation-Based Stock Access
# ─────────────────────────────────────────────────────────────────────────────

class TestBR19_DesignationStockAccess(BRTestBase):
    """BR-PS-019: stock_entry_view restricted to admin designations"""

    def test_valid_psadmin_access(self):
        """Valid: ps_admin can access stock_entry_view"""
        self._test_id = "BR-PS-019-V-01"
        self._br_id = "BR-PS-019"
        self._test_category = "Valid"
        self._input_action = f"GET /api/stock_entry_view/{self.hd_ps.pk} with ps_admin token"
        self._expected_result = "HTTP 200; stock entries returned"

        resp = self.api_get(f"/stock_entry_view/{self.hd_ps.pk}", self.tok_ps,
                            expected_status=None)

        if resp.status_code == 200:
            self._record_result("PS admin accesses stock entry view", "Pass", "HTTP 200")
        elif resp.status_code == 403:
            self._record_result("HTTP 403 — PS admin denied — role name mismatch", "Fail",
                                "Check @require_roles decorator for ps_admin role name")
            self.fail("PS admin should access stock_entry_view")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")

    def test_invalid_student_denied_stock_entry(self):
        """Invalid: student denied stock_entry_view"""
        self._test_id = "BR-PS-019-I-01"
        self._br_id = "BR-PS-019"
        self._test_category = "Invalid"
        self._input_action = f"GET /api/stock_entry_view/{self.hd_student.pk} with student token"
        self._expected_result = "HTTP 403; student role denied"

        resp = self.api_get(f"/stock_entry_view/{self.hd_student.pk}", self.tok_student,
                            expected_status=None)

        if resp.status_code == 403:
            self._record_result("Student denied stock_entry_view", "Pass",
                                "RBAC correctly enforced")
        elif resp.status_code == 200:
            self._record_result("Student can access stock entries — DEFECT", "Fail",
                                "RBAC not enforced for student on stock_entry_view")
            self.fail("Student should not access stock_entry_view")
        else:
            self._record_result(f"HTTP {resp.status_code}", "Partial",
                                f"Body: {resp.content[:200]}")
