"""
config.py  –  Runtime configuration loaded entirely from environment variables.

Copy .env.example to .env and fill in your values for local development.
For GitHub Actions, set these as repository Secrets.
"""
import os
import json

# ---------------------------------------------------------------------------
# CREDENTIALS  –  never hard-code these
# ---------------------------------------------------------------------------
CLIENT_ID     = os.environ.get("QUIRE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("QUIRE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("QUIRE_REFRESH_TOKEN")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# ---------------------------------------------------------------------------
# EMAIL CONFIG
# ---------------------------------------------------------------------------
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "your-sender@gmail.com")

# Comma-separated recipient list loaded from env var
# Example: EMAIL_RECIPIENTS="alice@company.com,bob@company.com"
_recipients_raw = os.environ.get("EMAIL_RECIPIENTS", "")
EMAIL_RECIPIENTS = [r.strip() for r in _recipients_raw.split(",") if r.strip()]

# ---------------------------------------------------------------------------
# PERFORMANCE TARGETS
# ---------------------------------------------------------------------------
TARGET_WEEKLY  = float(os.environ.get("TARGET_WEEKLY",  "40.0"))
TARGET_MONTHLY = float(os.environ.get("TARGET_MONTHLY", "171.4"))

# Comma-separated list of team members highlighted in the staff summary section
# Example: SPECIAL_STAFF="Alice,Bob,Carol"
_special_raw  = os.environ.get("SPECIAL_STAFF", "")
SPECIAL_STAFF = [n.strip() for n in _special_raw.split(",") if n.strip()]

# ---------------------------------------------------------------------------
# PROJECTS MAPPING
# Loaded from env var as JSON: PROYECTOS_OBJETIVO='{"oid1":"Project A","oid2":"Project B"}'
# Each key is a Quire project OID; each value is the display name.
# ---------------------------------------------------------------------------
_projects_raw     = os.environ.get("PROYECTOS_OBJETIVO", "{}")
PROYECTOS_OBJETIVO: dict = json.loads(_projects_raw)

# ---------------------------------------------------------------------------
# LOGIC LISTS
# ---------------------------------------------------------------------------

# Comma-separated list of valid assignee names (must match Quire exactly)
# Example: ASSIGNEE_NAMES="Alice,Bob,Carol,Dan"
_assignees_raw = os.environ.get(
    "ASSIGNEE_NAMES",
    "Assignee1,Assignee2,Assignee3"
)
ASSIGNEE_NAMES = [n.strip() for n in _assignees_raw.split(",") if n.strip()]

ALLOWED_TAGS = [
    "Assembly", "Design", "Documentation", "Electrical", "Engineering",
    "Fabrication", "General Work", "Machining", "Plan & Prep",
    "Programming", "Purchasing", "Subcontractor", "Wiring",
]

# Map tags to default assignees when no explicit assignment exists (Fallback Rule Level 3)
# Loaded from env var as JSON: RULE_MAPPING='{"Wiring":"Alice","Machining":"Bob"}'
_rule_raw    = os.environ.get("RULE_MAPPING", "{}")
RULE_MAPPING: dict = json.loads(_rule_raw)

# Name normalization map – use to canonicalize alternate spellings/nicknames
# Loaded from env var as JSON: NAME_NORMALIZATION='{"Nick":"Full Name","Alias":"Canonical"}'
_norm_raw          = os.environ.get("NAME_NORMALIZATION", "{}")
NAME_NORMALIZATION: dict = json.loads(_norm_raw)

# ---------------------------------------------------------------------------
# EXCLUSION LIST  –  tasks matching these names exactly are ignored
# ---------------------------------------------------------------------------
EXCLUSION_LIST = [
    "Purchasing", "DESIGN", "General Working", "Training",
    "Make/update OMM", "Documentation",
    "Create Preliminary Sketches and Review", "Project Startup",
    "Define Client Requirements", "Design",
    "Specify Key Functionalities",
    "Confirm Delivery Timeline with Client", "Obtain Scope Approval",
    "Register Project in QuickBooks and Quire", "Materials Management",
    "Review and Approve BOM", "Request Quotes and Validate Costs",
    "Generate Purchase Orders", "Assign Storage Space",
    "Label Materials and Assign to Project", "Design and Schematics",
    "Design Electrical, Hydraulic and DAQ Schematics",
    "Develop 3D Models and Renders", "Engineering Department Approval",
    "Client Review (if applicable)", "Fabrication and Assembly",
    "Cut and Machine Parts", "Assemble Electrical and Mechanical Components",
    "Verify Alignment and Preliminary Functionality",
    "Internal Assembly Approval",
    "Documentation and OMM", "Write OMM", "Print OMM",
    "Documentation Review and Approval",
    "Package Documentation with Equipment",
    "Closing and Delivery", "Perform Scope Compliance Checklist",
    "Take Photos and Videos of Final Equipment",
    "Schedule Delivery with Client",
    "Update Database and Change Project Status",
    "Upload Final Project Photos to Website and Social Media",
    "Check BOM", "DAQ Consoles", "General Working",
    "Welding", "Planning", "Tubing", "Time Log",
    "Complete OMM", "Fabricar", "Instalar", "Hoses", "Cabinet",
    "Hydraulic system", "Tuberias", "BOM", "Drain pump",
    "Main motor and pump", "Motor Pump", "Drain tank",
    "Main Tank (Resevoir)", "Heat exchanger", "insulation",
    "Actividades de cierre", "Contract Labor",
    "Panels", "Leaks", "Remove skin", "Schematic and Drawings",
    "8. Drain system", "9. Return system", "7. Main motor",
    "10. Accesories", "6. Motor drive", "5. Box 1 - DAQ",
    "4. Box 1 - Electrical", "3. Button box", "2. Lower panel",
    "1. Upper panel", "4. Electrical box", "5. Main motor + pump",
    "6. Drain system", "7. Return system", "8. Accessories",
    "9. Wiring", "10. Tubing", "5. Accessories",
    "4. Electrical system", "3. Back Drive Module",
    "2. High Torque Module", "1. Structure",
]
