"""
config.py — the ONLY file edited when porting this app to a new environment.

Everything source-specific (paths, table names, credentials, query text)
lives here. app.py and data.py must never reference a concrete data source.
"""

# ═══════════════════════════════════════════════════════════════════════════
# EDIT THIS BLOCK WHEN PORTING
# ═══════════════════════════════════════════════════════════════════════════

# ── Layer 1 — descriptions (curated) ─────────────────────────────────────────
# One of: "csv_local" | "excel_local" | "excel_stage" | "snowflake_table"
DESCRIPTIONS_SOURCE = "csv_local"

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
# (including blank) is treated as not approved.
DESCRIPTION_MAP = {
    "column_name": "Column Name",
    "description": "Description",
    "tags": "Tags",
    "steward": "Steward",
    "approved": "Approved",
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
