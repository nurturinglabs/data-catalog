"""
config.py — the ONLY file edited when porting this app to a new environment.

Everything source-specific (paths, table names, credentials, query text)
lives here. app.py and data.py must never reference a concrete data source.
"""

# ═══════════════════════════════════════════════════════════════════════════
# EDIT THIS BLOCK WHEN PORTING
# ═══════════════════════════════════════════════════════════════════════════

# ── Layer 1 — descriptions (curated) ─────────────────────────────────────────
# One of: "csv_local" | "excel_local" | "excel_stage" | "snowflake_table" |
# "workflow_table"
#
# "workflow_table" reads descriptions from the Layer 4 documentation
# workflow below (the Documentation workspace page's assignment table),
# filtered to rows with status == "Approved" — this is the single source of
# truth the workspace page writes to and the catalog reads from, so a
# newly-approved description shows up here with no separate store to keep
# in sync. This is the default; the other sources remain available for
# porting to a standalone descriptions feed instead.
DESCRIPTIONS_SOURCE = "workflow_table"

DESC_CSV_LOCAL = {
    "path": "sample_data/descriptions.csv",
}

DESC_EXCEL_LOCAL = {
    "path": "sample_data/descriptions.xlsx",
    "sheet": 0,
}

DESC_EXCEL_STAGE = {
    "stage_path": "@MY_DB.MY_SCHEMA.MY_STAGE/descriptions.xlsx",
    "sheet": 0,
}

DESC_SNOWFLAKE_TABLE = {
    "table": "MY_DB.MY_SCHEMA.COLUMN_DESCRIPTIONS",
}

# Canonical field -> header name in the raw description source.
# Required: column_name, description. Optional: tags, steward, approved.
# approved accepts TRUE/YES/Y/1/APPROVED/X (case-insensitive); anything else
# (including blank) is treated as not approved. Mapped to the workflow
# table's own "status" column here — its value is literally the string
# "Approved" once a row clears review, which already reads as truthy above,
# so no separate boolean column is needed.
#
# Switching DESCRIPTIONS_SOURCE back to "csv_local" (or another source)
# needs this map updated to match that source's own headers, e.g.:
#   {"column_name": "Column Name", "description": "Description",
#    "tags": "Tags", "steward": "Steward", "approved": "Approved"}
DESCRIPTION_MAP = {
    "column_name": "column_name",
    "description": "description",
    "approved": "status",
}

TAGS_DELIMITER = ","

# ── Layer 2 — structure (harvested, live) ───────────────────────────────────
# One of: "information_schema" | "information_schema_union" | "local_csv" | "snapshot_table"
STRUCTURE_SOURCE = "local_csv"

STRUCT_LOCAL_CSV = {
    "path": "sample_data/structure.csv",
}

STRUCT_SNAPSHOT_TABLE = {
    "table": "MY_DB.MY_SCHEMA.STRUCTURE_SNAPSHOT",
}

# Default query against SNOWFLAKE.ACCOUNT_USAGE.COLUMNS (org-wide, ~90 min
# latency, needs IMPORTED PRIVILEGES on the SNOWFLAKE database). Used when
# STRUCTURE_SOURCE == "information_schema".
STRUCTURE_QUERY = """
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE
FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS
WHERE DELETED IS NULL
  AND TABLE_SCHEMA <> 'INFORMATION_SCHEMA'
"""

# Databases to pull structure from when STRUCTURE_SOURCE ==
# "information_schema_union" — each database's own INFORMATION_SCHEMA.COLUMNS
# is queried directly (real-time, no ACCOUNT_USAGE grant needed) and the
# results are combined with UNION ALL. Also drives the database filter row
# in the UI (app.py reads this list, never derives it from the data).
STRUCTURE_DATABASES = ["FINANCE_DB", "HR_DB", "SALES_DB"]

# Canonical field -> header name in the raw structure source.
STRUCTURE_MAP = {
    "database": "TABLE_CATALOG",
    "schema": "TABLE_SCHEMA",
    "table": "TABLE_NAME",
    "column_name": "COLUMN_NAME",
    "data_type": "DATA_TYPE",
}

# If non-empty, structure is restricted to these databases (injected into the
# SQL WHERE for information_schema / information_schema_union; filtered in
# pandas for csv/table sources). Empty = unrestricted.
DATABASE_ALLOWLIST: list[str] = []

# ── Layer 3 — usage (who reads this, optional) ───────────────────────────────
# Master switch. When False, the usage load is skipped entirely and all
# "Used by" UI is hidden — a clean way to turn this layer off.
USAGE_ENABLED = True

# One of: "local_csv" | "access_history" | "snapshot_table"
# There is no Snowflake connection available yet, so this defaults to the
# local synthetic file. Switching to "access_history" later is a config-only
# change — no code changes required — exactly like STRUCTURE_SOURCE.
USAGE_SOURCE = "local_csv"

USAGE_LOCAL_CSV = {
    "path": "sample_data/usage.csv",
}

USAGE_SNAPSHOT_TABLE = {
    "table": "CATALOG_DB.GOVERNANCE.USAGE_SNAPSHOT",
}

# ACCESS_HISTORY-based query used when USAGE_SOURCE == "access_history".
# This is a STARTING TEMPLATE, not guaranteed-final SQL — the JSON paths and
# the consumer-labeling heuristic (the query_tag CASE expression below) must
# be validated against real ACCESS_HISTORY data in your account before
# relying on it. Requires Enterprise Edition, IMPORTED PRIVILEGES ON DATABASE
# SNOWFLAKE, and tolerance for ACCESS_HISTORY's normal latency. The
# consumer-type heuristic only works as well as your org's query-tagging
# conventions — edit the CASE expression to match how your team tags
# Streamlit/dbt/dashboard jobs.
USAGE_QUERY = """
SELECT
    cols.value:"columnName"::string   AS column_name,
    obj.value:"objectName"::string    AS table_name,
    COALESCE(qh.query_tag, ah.user_name) AS consumer_name,
    CASE
        WHEN qh.query_tag ILIKE '%streamlit%' THEN 'Streamlit app'
        WHEN qh.query_tag ILIKE '%dbt%'       THEN 'dbt model'
        WHEN qh.query_tag ILIKE '%tableau%'
          OR qh.query_tag ILIKE '%powerbi%'
          OR qh.query_tag ILIKE '%sigma%'     THEN 'Dashboard'
        WHEN qh.query_type = 'SELECT'
          AND qh.scheduled = TRUE             THEN 'Scheduled query'
        ELSE 'User / ad-hoc'
    END                                AS consumer_type,
    MAX(ah.query_start_time)::string   AS last_used,
    COUNT(*)                           AS query_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    ON ah.query_id = qh.query_id
, LATERAL FLATTEN(input => ah.base_objects_accessed) obj
, LATERAL FLATTEN(input => obj.value:"columns") cols
WHERE ah.query_start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND obj.value:"objectDomain"::string = 'Table'
GROUP BY 1, 2, 3, 4
"""

# Canonical field -> header name in the raw usage source.
# Required: column_name, consumer_name, consumer_type.
# Optional: table, last_used, query_count.
USAGE_MAP = {
    "column_name": "column_name",
    "table": "table",
    "consumer_name": "consumer_name",
    "consumer_type": "consumer_type",
    "last_used": "last_used",
    "query_count": "query_count",
}

# ── Layer 4 — documentation workflow (write side: assignment + authoring) ───
# The Documentation workspace page's own read/write store: a coordinator
# assigns columns to people, people fill in descriptions, and an approved
# row becomes the description Layer 1 reads (see DESCRIPTIONS_SOURCE above).
# One of: "local_csv" | "snowflake_table"
WORKFLOW_SOURCE = "local_csv"

WORKFLOW_LOCAL_CSV = {
    "path": "sample_data/assignments.csv",
}

WORKFLOW_TABLE = {
    "table": "CATALOG_DB.GOVERNANCE.COLUMN_ASSIGNMENTS",
}

# People available to assign columns to, until this is pulled from a real
# directory (e.g. a Snowflake role/user list).
WORKFLOW_ASSIGNEES = ["Priya", "Deepak", "Marcus", "Elena"]

# ── Join / display ───────────────────────────────────────────────────────────
# One of: "column_name" | "schema.column" | "table.column"
JOIN_GRAIN = "column_name"

# "structure"   -> show all physical columns, surface undocumented ones
# "descriptions" -> documented columns only
CATALOG_SPINE = "structure"

# Cap on rows pulled from the structure source; if exceeded, truncate + warn.
MAX_STRUCTURE_ROWS = 50_000

# st.cache_data(ttl=...) in seconds.
CACHE_TTL_SECONDS = 600

# ── Branding ──────────────────────────────────────────────────────────────────
APP_TITLE = "Almanac"
APP_SUBTITLE = "Curated meanings, live structure"
PRIMARY_COLOR = "#003366"
ACCENT_COLOR = "#FFB500"

# Optional path to a local logo image (png/svg/jpg) shown top-left of the
# header, in place of HEADER_ICON. Leave "" to use HEADER_ICON instead.
HEADER_LOGO_PATH = ""
HEADER_ICON = "📚"

# ═══════════════════════════════════════════════════════════════════════════
# END EDIT BLOCK
# ═══════════════════════════════════════════════════════════════════════════
