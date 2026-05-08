"""
runner.py — Custom Django Test Runner for PS1 Module
DO NOT EDIT — This is framework infrastructure.

Reads YAML spec files and generates 7 CSV deliverable sheets automatically.
Usage:
  python manage.py test applications.ps1.tests -v 2 \\
    --testrunner=applications.ps1.tests.runner.ReportingTestRunner
"""

import os
import csv
import sys
import json
import time
import traceback
import unittest
from datetime import datetime
from pathlib import Path

import yaml
from django.test.runner import DiscoverRunner

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
SPECS = BASE / "specs"
REPORTS = BASE / "reports"
TESTER_NAME = os.environ.get("TESTER_NAME", "Arjav Jain")
MODULE_NAME = "PS1 — Purchase & Store"
GROUP = "G1"
LLM = "Gemini / Antigravity (Google DeepMind)"


# ─────────────────────────────────────────────────────────────────────────────
# Custom Result Collector
# ─────────────────────────────────────────────────────────────────────────────

class CollectingTestResult(unittest.TextTestResult):
    """Extends TextTestResult to capture test metadata from _record_result calls."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.collected = []  # list of result dicts

    def startTest(self, test):
        super().startTest(test)
        # Reset metadata on the test instance
        for attr in [
            "_test_id", "_uc_id", "_br_id", "_wf_id", "_test_category",
            "_scenario", "_preconditions", "_input_action", "_expected_result",
            "_actual_result", "_status", "_evidence", "_tester",
        ]:
            if not hasattr(test, attr):
                setattr(test, attr, "")

    def addSuccess(self, test):
        super().addSuccess(test)
        self._collect(test, "Pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._collect(test, "Fail", evidence=str(err[1])[:300])

    def addError(self, test, err):
        super().addError(test, err)
        self._collect(test, "Error", evidence=str(err[1])[:300])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._collect(test, "Skip", evidence=reason)

    def _collect(self, test, final_status, evidence=None):
        # Prefer the test's own _status if it called _record_result
        status = getattr(test, "_status", None) or final_status
        self.collected.append({
            "test_id": getattr(test, "_test_id", test.id().split(".")[-1]),
            "source_type": self._detect_source_type(test),
            "source_id": (
                getattr(test, "_uc_id", "")
                or getattr(test, "_br_id", "")
                or getattr(test, "_wf_id", "")
            ),
            "test_category": getattr(test, "_test_category", ""),
            "scenario": getattr(test, "_scenario", ""),
            "preconditions": getattr(test, "_preconditions", ""),
            "input_action": getattr(test, "_input_action", ""),
            "expected_result": getattr(test, "_expected_result", ""),
            "actual_result": getattr(test, "_actual_result", final_status),
            "status": status,
            "evidence": getattr(test, "_evidence", "") or (evidence or ""),
            "tester": getattr(test, "_tester", TESTER_NAME),
        })

    @staticmethod
    def _detect_source_type(test):
        mod = type(test).__module__.lower()
        if "use_case" in mod:
            return "UC"
        if "business_rule" in mod:
            return "BR"
        if "workflow" in mod:
            return "WF"
        return "UC"


# ─────────────────────────────────────────────────────────────────────────────
# Report Generator
# ─────────────────────────────────────────────────────────────────────────────

def _load_yaml(filename):
    path = SPECS / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _write_csv(filename, fieldnames, rows):
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def generate_reports(collected):
    """Generate all 7 CSV deliverable sheets from collected test data."""
    uc_spec  = _load_yaml("use_cases.yaml").get("use_cases", [])
    br_spec  = _load_yaml("business_rules.yaml").get("business_rules", [])
    wf_spec  = _load_yaml("workflows.yaml").get("workflows", [])

    uc_results = [r for r in collected if r["source_type"] == "UC"]
    br_results = [r for r in collected if r["source_type"] == "BR"]
    wf_results = [r for r in collected if r["source_type"] == "WF"]

    pass_count    = sum(1 for r in collected if r["status"] == "Pass")
    fail_count    = sum(1 for r in collected if r["status"] in ("Fail", "Error"))
    partial_count = sum(1 for r in collected if r["status"] == "Partial")
    skip_count    = sum(1 for r in collected if r["status"] == "Skip")
    total_run     = len(collected)

    num_uc = len(uc_spec)
    num_br = len(br_spec)
    num_wf = len(wf_spec)
    req_uc = num_uc * 3
    req_br = num_br * 2
    req_wf = num_wf * 2
    total_req = req_uc + req_br + req_wf

    des_uc = len(uc_results)
    des_br = len(br_results)
    des_wf = len(wf_results)

    uc_adeq = f"{(des_uc / req_uc * 100):.1f}%" if req_uc else "N/A"
    br_adeq = f"{(des_br / req_br * 100):.1f}%" if req_br else "N/A"
    wf_adeq = f"{(des_wf / req_wf * 100):.1f}%" if req_wf else "N/A"
    pass_rate = f"{(pass_count / total_run * 100):.1f}%" if total_run else "N/A"

    # ── Sheet 1: Module_Test_Summary ─────────────────────────────────────────
    summary_rows = [
        {"Metric": "Module", "Value": MODULE_NAME},
        {"Metric": "Group", "Value": GROUP},
        {"Metric": "LLM Used", "Value": LLM},
        {"Metric": "Tester", "Value": TESTER_NAME},
        {"Metric": "Execution Date", "Value": datetime.now().strftime("%Y-%m-%d")},
        {"Metric": "Backend", "Value": "Django 3.1.5 — python manage.py test"},
        {"Metric": "Test File", "Value": "applications.ps1.tests"},
        {"Metric": "", "Value": ""},
        {"Metric": "Total Use Cases",    "Value": num_uc},
        {"Metric": "Total Business Rules","Value": num_br},
        {"Metric": "Total Workflows",    "Value": num_wf},
        {"Metric": "", "Value": ""},
        {"Metric": "Required UC Tests (3 × UC)",  "Value": req_uc},
        {"Metric": "Designed UC Tests",            "Value": des_uc},
        {"Metric": "UC Adequacy %",                "Value": uc_adeq},
        {"Metric": "", "Value": ""},
        {"Metric": "Required BR Tests (2 × BR)",  "Value": req_br},
        {"Metric": "Designed BR Tests",            "Value": des_br},
        {"Metric": "BR Adequacy %",                "Value": br_adeq},
        {"Metric": "", "Value": ""},
        {"Metric": "Required WF Tests (2 × WF)",  "Value": req_wf},
        {"Metric": "Designed WF Tests",            "Value": des_wf},
        {"Metric": "WF Adequacy %",                "Value": wf_adeq},
        {"Metric": "", "Value": ""},
        {"Metric": "Total Tests Required",  "Value": total_req},
        {"Metric": "Total Tests Executed",  "Value": total_run},
        {"Metric": "Total Pass",            "Value": pass_count},
        {"Metric": "Total Partial",         "Value": partial_count},
        {"Metric": "Total Fail",            "Value": fail_count},
        {"Metric": "Total Skipped",         "Value": skip_count},
        {"Metric": "Strict Pass Rate %",    "Value": pass_rate},
    ]
    _write_csv("Module_Test_Summary.csv", ["Metric", "Value"], summary_rows)

    # ── Sheet 2: UC_Test_Design ───────────────────────────────────────────────
    uc_design_rows = []
    for uc in uc_spec:
        uid = uc.get("id", "")
        title = uc.get("title", "")
        for i, hp in enumerate(uc.get("happy_paths", []), 1):
            uc_design_rows.append({
                "Test ID": f"{uid}-HP-{i:02d}",
                "UC ID": uid,
                "Test Category": "Happy Path",
                "Scenario": hp.get("scenario", ""),
                "Preconditions": hp.get("preconditions", uc.get("preconditions", "")),
                "Input / Action": hp.get("input_action", ""),
                "Expected Result": hp.get("expected_result", ""),
            })
        for i, ap in enumerate(uc.get("alternate_paths", []), 1):
            uc_design_rows.append({
                "Test ID": f"{uid}-AP-{i:02d}",
                "UC ID": uid,
                "Test Category": "Alternate Path",
                "Scenario": ap.get("scenario", ""),
                "Preconditions": ap.get("preconditions", uc.get("preconditions", "")),
                "Input / Action": ap.get("input_action", ""),
                "Expected Result": ap.get("expected_result", ""),
            })
        for i, ex in enumerate(uc.get("exception_paths", []), 1):
            uc_design_rows.append({
                "Test ID": f"{uid}-EX-{i:02d}",
                "UC ID": uid,
                "Test Category": "Exception",
                "Scenario": ex.get("scenario", ""),
                "Preconditions": ex.get("preconditions", ""),
                "Input / Action": ex.get("input_action", ""),
                "Expected Result": ex.get("expected_result", ""),
            })
    _write_csv("UC_Test_Design.csv",
               ["Test ID", "UC ID", "Test Category", "Scenario",
                "Preconditions", "Input / Action", "Expected Result"],
               uc_design_rows)

    # ── Sheet 3: BR_Test_Design ───────────────────────────────────────────────
    br_design_rows = []
    for br in br_spec:
        bid = br.get("id", "")
        for i, v in enumerate(br.get("valid_tests", []), 1):
            br_design_rows.append({
                "Test ID": f"{bid}-V-{i:02d}",
                "BR ID": bid,
                "Test Category": "Valid",
                "Input / Action": v.get("input_action", ""),
                "Expected Result": v.get("expected_result", ""),
            })
        for i, inv in enumerate(br.get("invalid_tests", []), 1):
            br_design_rows.append({
                "Test ID": f"{bid}-I-{i:02d}",
                "BR ID": bid,
                "Test Category": "Invalid",
                "Input / Action": inv.get("input_action", ""),
                "Expected Result": inv.get("expected_result", ""),
            })
    _write_csv("BR_Test_Design.csv",
               ["Test ID", "BR ID", "Test Category", "Input / Action", "Expected Result"],
               br_design_rows)

    # ── Sheet 4: WF_Test_Design ───────────────────────────────────────────────
    wf_design_rows = []
    for wf in wf_spec:
        wid = wf.get("id", "")
        for i, e2e in enumerate(wf.get("e2e_tests", []), 1):
            wf_design_rows.append({
                "Test ID": f"{wid}-E2E-{i:02d}",
                "WF ID": wid,
                "Test Category": "End-to-End",
                "Scenario": e2e.get("scenario", "").strip(),
                "Expected Final State": e2e.get("expected_final_state", "").strip(),
            })
        for i, neg in enumerate(wf.get("negative_tests", []), 1):
            wf_design_rows.append({
                "Test ID": f"{wid}-NEG-{i:02d}",
                "WF ID": wid,
                "Test Category": "Negative",
                "Scenario": neg.get("scenario", "").strip(),
                "Expected Final State": neg.get("expected_final_state", "").strip(),
            })
    _write_csv("WF_Test_Design.csv",
               ["Test ID", "WF ID", "Test Category", "Scenario", "Expected Final State"],
               wf_design_rows)

    # ── Sheet 5: Test_Execution_Log ───────────────────────────────────────────
    exec_rows = []
    for r in collected:
        exec_rows.append({
            "Test ID": r["test_id"],
            "Source Type": r["source_type"],
            "Source ID": r["source_id"],
            "Expected Result": r["expected_result"],
            "Actual Result": r["actual_result"],
            "Status": r["status"],
            "Evidence": r["evidence"],
            "Tester": r["tester"],
        })
    _write_csv("Test_Execution_Log.csv",
               ["Test ID", "Source Type", "Source ID", "Expected Result",
                "Actual Result", "Status", "Evidence", "Tester"],
               exec_rows)

    # ── Sheet 6: Defect_Log ───────────────────────────────────────────────────
    defect_rows = []
    defect_id = 1
    for r in collected:
        if r["status"] in ("Fail", "Error", "Partial"):
            severity = "Critical" if r["status"] == "Error" else (
                "High" if r["status"] == "Fail" else "Medium"
            )
            defect_rows.append({
                "Defect ID": f"DEF-{defect_id:03d}",
                "Related Test ID": r["test_id"],
                "Related Artifact": r["source_id"],
                "Severity": severity,
                "Description": (
                    f"Test '{r['test_id']}' failed. "
                    f"Expected: {r['expected_result']}. "
                    f"Actual: {r['actual_result']}."
                ),
                "Suggested Fix": r["evidence"],
            })
            defect_id += 1
    _write_csv("Defect_Log.csv",
               ["Defect ID", "Related Test ID", "Related Artifact",
                "Severity", "Description", "Suggested Fix"],
               defect_rows)

    # ── Sheet 7: Artifact_Evaluation ─────────────────────────────────────────
    eval_rows = []

    def _evaluate_uc(uid):
        tests = [r for r in uc_results if r["source_id"] == uid]
        if not tests:
            return "Not Implemented", 0, 0, 0
        passed  = sum(1 for t in tests if t["status"] == "Pass")
        partial = sum(1 for t in tests if t["status"] == "Partial")
        failed  = sum(1 for t in tests if t["status"] in ("Fail", "Error"))
        if failed == 0 and partial == 0:
            status = "Implemented Correctly"
        elif passed == 0:
            status = "Not Implemented" if failed == len(tests) else "Incorrectly Implemented"
        else:
            status = "Partially Implemented"
        return status, passed, partial, failed

    def _evaluate_br(bid):
        tests = [r for r in br_results if r["source_id"] == bid]
        if not tests:
            return "Not Enforced", 0, 0, 0
        passed  = sum(1 for t in tests if t["status"] == "Pass")
        partial = sum(1 for t in tests if t["status"] == "Partial")
        failed  = sum(1 for t in tests if t["status"] in ("Fail", "Error"))
        if failed == 0 and partial == 0:
            status = "Enforced Correctly"
        elif passed == 0:
            status = "Not Enforced"
        else:
            status = "Partially Enforced"
        return status, passed, partial, failed

    def _evaluate_wf(wid):
        tests = [r for r in wf_results if r["source_id"] == wid]
        if not tests:
            return "Missing", 0, 0, 0
        passed  = sum(1 for t in tests if t["status"] == "Pass")
        partial = sum(1 for t in tests if t["status"] == "Partial")
        failed  = sum(1 for t in tests if t["status"] in ("Fail", "Error"))
        if failed == 0 and partial == 0:
            status = "Complete"
        elif passed == len(tests):
            status = "Complete"
        elif passed == 0 and failed == len(tests):
            status = "Missing"
        else:
            status = "Partial"
        return status, passed, partial, failed

    for uc in uc_spec:
        uid = uc.get("id", "")
        status, p, part, f = _evaluate_uc(uid)
        total = p + part + f
        eval_rows.append({
            "Artifact ID": uid,
            "Artifact Type": "Use Case",
            "Tests": total or (3 if uid else 0),
            "Pass": p,
            "Partial": part,
            "Fail": f,
            "Final Status": status,
            "Remarks": uc.get("title", ""),
        })
    for br in br_spec:
        bid = br.get("id", "")
        status, p, part, f = _evaluate_br(bid)
        total = p + part + f
        eval_rows.append({
            "Artifact ID": bid,
            "Artifact Type": "Business Rule",
            "Tests": total or 2,
            "Pass": p,
            "Partial": part,
            "Fail": f,
            "Final Status": status,
            "Remarks": br.get("title", ""),
        })
    for wf in wf_spec:
        wid = wf.get("id", "")
        status, p, part, f = _evaluate_wf(wid)
        total = p + part + f
        eval_rows.append({
            "Artifact ID": wid,
            "Artifact Type": "Workflow",
            "Tests": total or 2,
            "Pass": p,
            "Partial": part,
            "Fail": f,
            "Final Status": status,
            "Remarks": wf.get("title", ""),
        })

    _write_csv("Artifact_Evaluation.csv",
               ["Artifact ID", "Artifact Type", "Tests", "Pass", "Partial",
                "Fail", "Final Status", "Remarks"],
               eval_rows)

    return {
        "total": total_run,
        "pass": pass_count,
        "fail": fail_count,
        "partial": partial_count,
        "skip": skip_count,
        "defects": len(defect_rows),
        "uc_adequacy": uc_adeq,
        "br_adequacy": br_adeq,
        "wf_adequacy": wf_adeq,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Custom Test Runner
# ─────────────────────────────────────────────────────────────────────────────

class ReportingTestRunner(DiscoverRunner):
    """
    Drop-in replacement for DiscoverRunner that captures results and
    generates all 7 CSV report sheets automatically after the run.

    Usage:
      python manage.py test applications/ps1/tests/ -v 2 \\
        --testrunner=applications.ps1.tests.runner.ReportingTestRunner

    Uses fake_initial=True to skip broken legacy app initial migrations
    (e.g. central_mess.0001_initial creates 'Payments' table twice).
    """

    def setup_databases(self, **kwargs):
        """
        Override to disable DB serialization after migration.
        Django 3.1 serializes DB contents after migrating to support
        TransactionTestCase rollback. This fails when ORM models have fields that
        were not included in migrations (e.g. IndentFile fields added via Python).
        Since all our tests use TestCase (not TransactionTestCase), serialization is
        not needed.
        """
        from unittest.mock import patch

        def _no_serialize(*args, **kw):
            return ""

        with patch(
            "django.db.backends.base.creation.BaseDatabaseCreation.serialize_db_to_string",
            _no_serialize,
        ):
            return super().setup_databases(**kwargs)

    def get_resultclass(self):
        return CollectingTestResult

    def run_suite(self, suite, **kwargs):
        runner = self.test_runner(
            stream=sys.stderr,
            verbosity=self.verbosity,
            failfast=self.failfast,
        )
        result = runner.run(suite)
        return result

    def suite_result(self, suite, result, **kwargs):
        # Generate reports after the run
        print("\n" + "=" * 70)
        print("  GENERATING REPORT SHEETS...")
        print("=" * 70)

        collected = getattr(result, "collected", [])

        try:
            summary = generate_reports(collected)
            REPORTS.mkdir(exist_ok=True)
            print(f"\n  Reports written to: {REPORTS}/")
            print(f"  ├─ Module_Test_Summary.csv")
            print(f"  ├─ UC_Test_Design.csv")
            print(f"  ├─ BR_Test_Design.csv")
            print(f"  ├─ WF_Test_Design.csv")
            print(f"  ├─ Test_Execution_Log.csv")
            print(f"  ├─ Defect_Log.csv")
            print(f"  └─ Artifact_Evaluation.csv")
            print(f"\n  ┌─ SUMMARY ───────────────────────────────────")
            print(f"  │  Total Run:  {summary['total']}")
            print(f"  │  Pass:       {summary['pass']}")
            print(f"  │  Fail:       {summary['fail']}")
            print(f"  │  Partial:    {summary['partial']}")
            print(f"  │  Skipped:    {summary['skip']}")
            print(f"  │  Defects:    {summary['defects']}")
            print(f"  │  UC Adequacy: {summary['uc_adequacy']}")
            print(f"  │  BR Adequacy: {summary['br_adequacy']}")
            print(f"  │  WF Adequacy: {summary['wf_adequacy']}")
            print(f"  └─────────────────────────────────────────────")
        except Exception as e:
            print(f"  ERROR generating reports: {e}")
            traceback.print_exc()

        print("=" * 70 + "\n")
        return super().suite_result(suite, result, **kwargs)
