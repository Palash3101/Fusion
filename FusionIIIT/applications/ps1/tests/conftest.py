"""
conftest.py — Base test classes for PS1 Purchase & Store module tests.
Assignment 8 | G1 | Gemini / Antigravity

Provides:
  BaseModuleTestCase  — shared DB setup (users, designations, vendor)
  UCTestBase          — adds UC metadata + _record_result / _test_id helpers
  BRTestBase          — adds BR metadata helpers
  WFTestBase          — adds WF metadata + step-tracking helpers
"""

import json
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone

from rest_framework.authtoken.models import Token

from applications.globals.models import (
    HoldsDesignation, Designation, DepartmentInfo, ExtraInfo,
)

# ── Module-level result collector (read by runner.py) ────────────────────────
_RESULTS = []   # list of dicts appended by _record_result()


def _push_result(record: dict):
    _RESULTS.append(record)


# ── URL prefix ───────────────────────────────────────────────────────────────
API_BASE = "/purchase-and-store/api"


# ─────────────────────────────────────────────────────────────────────────────
# Base Setup
# ─────────────────────────────────────────────────────────────────────────────

class BaseModuleTestCase(TestCase):
    """
    Creates the minimal DB fixtures that every PS1 test needs.
    Override setUpTestData in subclasses to add module-specific objects.
    """

    # Prevent Django from attempting to serialize the full DB for rollback.
    # This fails when model fields added outside migrations exist in the ORM
    # but not in the serialized DB (e.g. IndentFile.indent_name).
    serialized_rollback = False

    @classmethod
    def setUpTestData(cls):
        # Department
        cls.dept, _ = DepartmentInfo.objects.get_or_create(name="CSE")

        # Designations
        cls.des_student, _    = Designation.objects.get_or_create(name="student")
        cls.des_deptadmin, _  = Designation.objects.get_or_create(name="deptadmin_cse")
        cls.des_psadmin, _    = Designation.objects.get_or_create(name="ps_admin")
        cls.des_hod, _        = Designation.objects.get_or_create(name="HOD")
        cls.des_director, _   = Designation.objects.get_or_create(name="Director")
        cls.des_accounts, _   = Designation.objects.get_or_create(name="Accounts Admin")
        cls.des_auditor, _    = Designation.objects.get_or_create(name="Auditor")

        # Users
        cls.student_user   = cls._make_user("tc_student",  cls.des_student)
        cls.admin_user     = cls._make_user("tc_admin",    cls.des_deptadmin)
        cls.ps_user        = cls._make_user("tc_psadmin",  cls.des_psadmin)
        cls.hod_user       = cls._make_user("tc_hod",      cls.des_hod)
        cls.director_user  = cls._make_user("tc_director", cls.des_director)
        cls.auditor_user   = cls._make_user("tc_auditor",  cls.des_auditor)

        # Tokens
        cls.tok_student  = Token.objects.get_or_create(user=cls.student_user)[0].key
        cls.tok_admin    = Token.objects.get_or_create(user=cls.admin_user)[0].key
        cls.tok_ps       = Token.objects.get_or_create(user=cls.ps_user)[0].key
        cls.tok_hod      = Token.objects.get_or_create(user=cls.hod_user)[0].key
        cls.tok_director = Token.objects.get_or_create(user=cls.director_user)[0].key
        cls.tok_auditor  = Token.objects.get_or_create(user=cls.auditor_user)[0].key

        # HoldsDesignation IDs (used in several URL paths)
        cls.hd_student  = HoldsDesignation.objects.get(user=cls.student_user)
        cls.hd_admin    = HoldsDesignation.objects.get(user=cls.admin_user)
        cls.hd_ps       = HoldsDesignation.objects.get(user=cls.ps_user)
        cls.hd_hod      = HoldsDesignation.objects.get(user=cls.hod_user)
        cls.hd_auditor  = HoldsDesignation.objects.get(user=cls.auditor_user)

    @classmethod
    def _make_user(cls, username, designation):
        user, _ = User.objects.get_or_create(username=username)
        user.set_password("testpass123")
        user.save()
        # ExtraInfo uses CharField PK = id (roll number / username)
        ExtraInfo.objects.get_or_create(
            id=username,
            defaults={
                "user": user,
                "department": cls.dept,
                "user_type": "staff",
            },
        )
        HoldsDesignation.objects.get_or_create(
            user=user,
            designation=designation,
            defaults={"working": user},   # working = FK to User, same user
        )
        return user

    # ── API helpers ───────────────────────────────────────────────────────────

    def _client(self, token):
        c = Client()
        c.defaults["HTTP_AUTHORIZATION"] = f"Token {token}"
        return c

    def api_get(self, path, token, expected_status=200):
        c = self._client(token)
        resp = c.get(f"{API_BASE}{path}")
        if expected_status is not None:
            self.assertEqual(resp.status_code, expected_status,
                             f"GET {path} expected {expected_status}, got {resp.status_code}")
        return resp

    def api_post(self, path, token, data=None, expected_status=None, json_data=True):
        c = self._client(token)
        if json_data:
            resp = c.post(f"{API_BASE}{path}",
                          data=json.dumps(data or {}),
                          content_type="application/json")
        else:
            resp = c.post(f"{API_BASE}{path}", data=data or {})
        if expected_status is not None:
            self.assertIn(resp.status_code, expected_status if isinstance(expected_status, (list, tuple)) else [expected_status],
                          f"POST {path} expected {expected_status}, got {resp.status_code}")
        return resp

    def api_get_no_auth(self, path):
        c = Client()
        return c.get(f"{API_BASE}{path}")

    def api_post_no_auth(self, path, data=None):
        c = Client()
        return c.post(f"{API_BASE}{path}",
                      data=json.dumps(data or {}),
                      content_type="application/json")

    # ── Date helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def future_date(days=7):
        return (date.today() + timedelta(days=days)).isoformat()

    @staticmethod
    def past_date(days=1):
        return (date.today() - timedelta(days=days)).isoformat()

    # ── Assertion helpers ─────────────────────────────────────────────────────

    def assert_object_exists(self, model, **kwargs):
        self.assertTrue(
            model.objects.filter(**kwargs).exists(),
            f"{model.__name__} with {kwargs} not found in DB"
        )


# ─────────────────────────────────────────────────────────────────────────────
# UC Test Base
# ─────────────────────────────────────────────────────────────────────────────

class UCTestBase(BaseModuleTestCase):
    """Base class for all Use Case tests."""

    def setUp(self):
        # Metadata fields — must be set in each test method
        self._test_id = "UNSET"
        self._uc_id = "UNSET"
        self._test_category = "UNSET"
        self._scenario = ""
        self._preconditions = ""
        self._input_action = ""
        self._expected_result = ""
        self._actual_result = ""
        self._status = "Fail"
        self._evidence = ""
        self._tester = "Arjav Jain"

    def _record_result(self, actual_result, status, evidence=""):
        """Call at the end of each test to record the outcome."""
        self._actual_result = actual_result
        self._status = status
        self._evidence = evidence
        _push_result({
            "test_id": self._test_id,
            "source_type": "UC",
            "source_id": self._uc_id,
            "test_category": self._test_category,
            "scenario": self._scenario,
            "preconditions": self._preconditions,
            "input_action": self._input_action,
            "expected_result": self._expected_result,
            "actual_result": actual_result,
            "status": status,
            "evidence": evidence,
            "tester": self._tester,
        })


# ─────────────────────────────────────────────────────────────────────────────
# BR Test Base
# ─────────────────────────────────────────────────────────────────────────────

class BRTestBase(BaseModuleTestCase):
    """Base class for all Business Rule tests."""

    def setUp(self):
        self._test_id = "UNSET"
        self._br_id = "UNSET"
        self._test_category = "UNSET"
        self._input_action = ""
        self._expected_result = ""
        self._actual_result = ""
        self._status = "Fail"
        self._evidence = ""
        self._tester = "Arjav Jain"

    def _record_result(self, actual_result, status, evidence=""):
        self._actual_result = actual_result
        self._status = status
        self._evidence = evidence
        _push_result({
            "test_id": self._test_id,
            "source_type": "BR",
            "source_id": self._br_id,
            "test_category": self._test_category,
            "scenario": "",
            "preconditions": "",
            "input_action": self._input_action,
            "expected_result": self._expected_result,
            "actual_result": actual_result,
            "status": status,
            "evidence": evidence,
            "tester": self._tester,
        })


# ─────────────────────────────────────────────────────────────────────────────
# WF Test Base
# ─────────────────────────────────────────────────────────────────────────────

class WFTestBase(BaseModuleTestCase):
    """Base class for all Workflow tests."""

    def setUp(self):
        self._test_id = "UNSET"
        self._wf_id = "UNSET"
        self._test_category = "UNSET"
        self._scenario = ""
        self._expected_final_state = ""
        self._steps = []
        self._status = "Fail"
        self._evidence = ""
        self._tester = "Arjav Jain"

    def _add_step(self, step_num, action, expected, actual, passed):
        self._steps.append({
            "step": step_num, "action": action,
            "expected": expected, "actual": actual, "passed": passed,
        })

    def _all_steps_passed(self):
        return all(s["passed"] for s in self._steps)

    def _record_result(self, actual_result, status, evidence=""):
        steps_summary = " | ".join(
            f"Step{s['step']}({'OK' if s['passed'] else 'FAIL'}): {s['action']}"
            for s in self._steps
        )
        _push_result({
            "test_id": self._test_id,
            "source_type": "WF",
            "source_id": self._wf_id,
            "test_category": self._test_category,
            "scenario": self._scenario,
            "preconditions": "",
            "input_action": steps_summary,
            "expected_result": self._expected_final_state,
            "actual_result": actual_result,
            "status": status,
            "evidence": evidence or steps_summary,
            "tester": self._tester,
        })
