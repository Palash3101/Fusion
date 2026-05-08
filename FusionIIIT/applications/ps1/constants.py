# PS1 Module Constants
# Single source of truth for all shared constants used across the module.

DEPT_ADMIN_TO_DEPT = {
    "deptadmin_cse": "CSE",
    "deptadmin_ece": "ECE",
    "deptadmin_me": "ME",
    "deptadmin_sm": "SM",
    "deptadmin_design": "Design",
    "deptadmin_liberalarts": "Liberal Arts",
    "deptadmin_ns": "Natural Science",
}

DEPT_ADMIN_ROLES = [
    "deptadmin_cse",
    "deptadmin_ece",
    "deptadmin_me",
    "deptadmin_sm",
    "deptadmin_design",
    "deptadmin_liberalarts",
    "deptadmin_ns",
]

HOD_ROLES = [
    "HOD (CSE)",
    "HOD (ECE)",
    "HOD (ME)",
    "HOD (SM)",
    "HOD (Design)",
    "HOD (Liberal Arts)",
    "HOD (Natural Science)",
]

# T-16: Add HOD roles to authorized stock-read access (PSM-UC-017, BR-PS-003)
AUTHORIZED_ROLES = DEPT_ADMIN_ROLES + HOD_ROLES + ["ps_admin"]

# T-03: Cost threshold routing (BR-PS-004)
COST_THRESHOLD_DEPT_HEAD = 25000  # ≤25k → Dept Head only
COST_THRESHOLD_REGISTRAR = 100000  # 25k-100k → + Registrar
# >100k → + Director

# T-14: SLA deadlines in hours
SLA_DEPT_ADMIN_HOURS = 24
SLA_HOD_HOURS = 48
SLA_DIRECTOR_HOURS = 72
SLA_FINANCIAL_HOURS = 48

# T-15: Duplicate detection window (BR-PS-015)
DUPLICATE_DETECTION_WINDOW_HOURS = 24

# T-16: Asset capitalization threshold (BR-PS-016)
ASSET_CAPITALIZATION_THRESHOLD = 50000.00

# T-08: Tender threshold (BR-PS-008)
TENDER_THRESHOLD = 500000.00

# Auditor role (T-23)
AUDITOR_ROLE = "auditor"

PS1_MODULE = "ps1"

