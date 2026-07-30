"""
Regenerates the synthetic demo sources: structure.csv, descriptions.csv,
usage.csv, and assignments.csv. Run with: python sample_data/_generate.py

structure.csv is INFORMATION_SCHEMA-shaped physical schema for 3 synthetic
databases. descriptions.csv is a partial, human-authored description layer
covering roughly two-thirds of the distinct column names, so the demo shows a
non-trivial reverse index and coverage < 100% (kept for DESCRIPTIONS_SOURCE
values other than the default "workflow_table"). usage.csv is synthetic
"who reads this column" data spanning multiple consumer types, with a couple
of load-bearing columns, some single-consumer columns, and several documented
columns with no recorded usage at all. assignments.csv is the Documentation
workspace's own COLUMN_ASSIGNMENTS table — the default descriptions source —
seeded from the same structure with a realistic spread of statuses and
assignees; a handful of structural columns are deliberately left out of it so
the workspace page's live auto-seed/reconcile behavior has something to do.
"""

import datetime as _dt
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = _dt.date.today()


def _days_ago(n: int) -> str:
    return (TODAY - _dt.timedelta(days=n)).isoformat()

# (TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME) -> [COLUMN_NAME, ...]
# Column order within a table also implies a DATA_TYPE below.
TABLES = {
    ("SALES_DB", "PUBLIC", "CUSTOMERS"): [
        "CUSTOMER_ID", "FIRST_NAME", "LAST_NAME", "EMAIL", "PHONE",
        "ADDRESS", "CITY", "STATE", "ZIP_CODE", "CREATED_AT",
    ],
    ("SALES_DB", "PUBLIC", "ORDERS"): [
        "ORDER_ID", "CUSTOMER_ID", "ORDER_DATE", "STATUS", "TOTAL_AMOUNT",
        "SHIPPING_ADDRESS", "CREATED_AT",
    ],
    ("SALES_DB", "PUBLIC", "ORDER_ITEMS"): [
        "ORDER_ITEM_ID", "ORDER_ID", "PRODUCT_ID", "QUANTITY", "UNIT_PRICE",
    ],
    ("SALES_DB", "PUBLIC", "PRODUCTS"): [
        "PRODUCT_ID", "PRODUCT_NAME", "CATEGORY", "UNIT_PRICE", "SUPPLIER_ID",
    ],
    ("SALES_DB", "ANALYTICS", "CUSTOMER_SEGMENTS"): [
        "CUSTOMER_ID", "SEGMENT", "LIFETIME_VALUE", "LAST_SCORED_AT",
    ],
    ("SALES_DB", "ANALYTICS", "SALES_SUMMARY"): [
        "CUSTOMER_ID", "PERIOD", "TOTAL_SALES", "ORDER_COUNT",
    ],
    ("HR_DB", "PUBLIC", "EMPLOYEES"): [
        "EMPLOYEE_ID", "FIRST_NAME", "LAST_NAME", "EMAIL", "HIRE_DATE",
        "DEPARTMENT_ID", "MANAGER_ID", "SSN",
    ],
    ("HR_DB", "PUBLIC", "DEPARTMENTS"): [
        "DEPARTMENT_ID", "DEPARTMENT_NAME", "COST_CENTER",
    ],
    ("HR_DB", "PUBLIC", "PAYROLL"): [
        "PAYROLL_ID", "EMPLOYEE_ID", "PAY_PERIOD", "GROSS_PAY", "NET_PAY",
        "TAX_WITHHELD",
    ],
    ("FINANCE_DB", "PUBLIC", "INVOICES"): [
        "INVOICE_ID", "CUSIP", "VENDOR_ID", "INVOICE_DATE", "AMOUNT", "STATUS",
    ],
    ("FINANCE_DB", "PUBLIC", "PAYMENTS"): [
        "PAYMENT_ID", "CUSIP", "INVOICE_ID", "PAYMENT_DATE", "AMOUNT_PAID",
        "METHOD",
    ],
    ("FINANCE_DB", "PUBLIC", "VENDORS"): [
        "VENDOR_ID", "CUSIP", "VENDOR_NAME", "TAX_ID", "CONTACT_EMAIL",
    ],
    ("FINANCE_DB", "REPORTING", "GL_ENTRIES"): [
        "GL_ENTRY_ID", "CUSIP", "ACCOUNT_CODE", "DEBIT_AMOUNT",
        "CREDIT_AMOUNT", "POSTED_AT",
    ],
}

# Representative Snowflake data type per column name (used everywhere that
# column appears; a handful of columns intentionally vary by table to
# exercise the "representative / mode" data_type collapse logic).
DATA_TYPES = {
    "CUSTOMER_ID": "NUMBER(38,0)", "FIRST_NAME": "VARCHAR(100)",
    "LAST_NAME": "VARCHAR(100)", "EMAIL": "VARCHAR(255)",
    "PHONE": "VARCHAR(20)", "ADDRESS": "VARCHAR(255)", "CITY": "VARCHAR(100)",
    "STATE": "VARCHAR(2)", "ZIP_CODE": "VARCHAR(10)",
    "CREATED_AT": "TIMESTAMP_NTZ", "ORDER_ID": "NUMBER(38,0)",
    "ORDER_DATE": "DATE", "STATUS": "VARCHAR(20)",
    "TOTAL_AMOUNT": "NUMBER(12,2)", "SHIPPING_ADDRESS": "VARCHAR(255)",
    "ORDER_ITEM_ID": "NUMBER(38,0)", "PRODUCT_ID": "NUMBER(38,0)",
    "QUANTITY": "NUMBER(10,0)", "UNIT_PRICE": "NUMBER(12,2)",
    "PRODUCT_NAME": "VARCHAR(200)", "CATEGORY": "VARCHAR(100)",
    "SUPPLIER_ID": "NUMBER(38,0)", "SEGMENT": "VARCHAR(50)",
    "LIFETIME_VALUE": "NUMBER(12,2)", "LAST_SCORED_AT": "TIMESTAMP_NTZ",
    "PERIOD": "VARCHAR(7)", "TOTAL_SALES": "NUMBER(14,2)",
    "ORDER_COUNT": "NUMBER(10,0)", "EMPLOYEE_ID": "NUMBER(38,0)",
    "HIRE_DATE": "DATE", "DEPARTMENT_ID": "NUMBER(38,0)",
    "MANAGER_ID": "NUMBER(38,0)", "SSN": "VARCHAR(11)",
    "DEPARTMENT_NAME": "VARCHAR(100)", "COST_CENTER": "VARCHAR(20)",
    "PAYROLL_ID": "NUMBER(38,0)", "PAY_PERIOD": "VARCHAR(7)",
    "GROSS_PAY": "NUMBER(12,2)", "NET_PAY": "NUMBER(12,2)",
    "TAX_WITHHELD": "NUMBER(12,2)", "INVOICE_ID": "NUMBER(38,0)",
    "CUSIP": "VARCHAR(9)", "VENDOR_ID": "NUMBER(38,0)",
    "INVOICE_DATE": "DATE", "AMOUNT": "NUMBER(12,2)",
    "PAYMENT_ID": "NUMBER(38,0)", "PAYMENT_DATE": "DATE",
    "AMOUNT_PAID": "NUMBER(12,2)", "METHOD": "VARCHAR(20)",
    "VENDOR_NAME": "VARCHAR(200)", "TAX_ID": "VARCHAR(20)",
    "CONTACT_EMAIL": "VARCHAR(255)", "GL_ENTRY_ID": "NUMBER(38,0)",
    "ACCOUNT_CODE": "VARCHAR(20)", "DEBIT_AMOUNT": "NUMBER(12,2)",
    "CREDIT_AMOUNT": "NUMBER(12,2)", "POSTED_AT": "TIMESTAMP_NTZ",
}

# Curated descriptions: column_name -> (description, tags, steward, approved).
# Roughly two-thirds of distinct column names are documented; the rest are
# left out on purpose so coverage < 100%. `approved` is intentionally NOT a
# 1:1 mirror of the "Certified" tag — a handful of certified columns are
# still pending approval, and a couple of non-certified ones are approved,
# to demonstrate the two are independent signals.
DESCRIPTIONS = {
    "CUSTOMER_ID": ("Unique identifier for a customer account.", "Certified", "Data Governance", True),
    "FIRST_NAME": ("Given name of the individual.", "PII", "Data Governance", False),
    "LAST_NAME": ("Family name of the individual.", "PII", "Data Governance", False),
    "EMAIL": ("Primary email address on file.", "PII", "Data Governance", False),
    "PHONE": ("Primary phone number on file.", "PII", "Data Governance", False),
    "CITY": ("City component of the mailing address.", "", "Data Governance", False),
    "STATE": ("Two-letter US state code.", "", "Data Governance", False),
    "CREATED_AT": ("Timestamp the record was first created.", "", "", False),
    "ORDER_ID": ("Unique identifier for a customer order.", "Certified", "Sales Ops", True),
    "ORDER_DATE": ("Calendar date the order was placed.", "", "Sales Ops", False),
    "STATUS": ("Current lifecycle status of the record (e.g. OPEN, CLOSED).", "", "Sales Ops", False),
    "TOTAL_AMOUNT": ("Total order value in USD, including tax.", "Certified", "Sales Ops", False),
    "ORDER_ITEM_ID": ("Unique identifier for a single line item on an order.", "", "Sales Ops", False),
    "PRODUCT_ID": ("Unique identifier for a product SKU.", "Certified", "Sales Ops", False),
    "QUANTITY": ("Number of units ordered for this line item.", "", "", False),
    "UNIT_PRICE": ("List price per unit at time of order, in USD.", "", "Sales Ops", False),
    "PRODUCT_NAME": ("Human-readable product name.", "", "Sales Ops", False),
    "CATEGORY": ("Product category used for merchandising and reporting.", "", "", False),
    "SEGMENT": ("Marketing-assigned customer segment label.", "", "Marketing Analytics", False),
    "LIFETIME_VALUE": ("Modeled lifetime value of the customer, in USD.", "", "Marketing Analytics", False),
    "EMPLOYEE_ID": ("Unique identifier for an employee record.", "Certified", "People Analytics", True),
    "HIRE_DATE": ("Date the employee's current employment began.", "", "People Analytics", False),
    "DEPARTMENT_ID": ("Unique identifier for an organizational department.", "", "People Analytics", True),
    "MANAGER_ID": ("Employee ID of this employee's direct manager.", "", "People Analytics", False),
    "SSN": ("Social Security Number. Restricted access.", "PII", "People Analytics", False),
    "DEPARTMENT_NAME": ("Display name of the department.", "", "People Analytics", False),
    "PAYROLL_ID": ("Unique identifier for a payroll run line.", "", "People Analytics", False),
    "PAY_PERIOD": ("Pay period the payroll entry applies to (YYYY-MM).", "", "", False),
    "GROSS_PAY": ("Gross pay before deductions, in USD.", "", "People Analytics", False),
    "NET_PAY": ("Net pay after deductions, in USD.", "", "People Analytics", False),
    "INVOICE_ID": ("Unique identifier for a vendor invoice.", "Certified", "Finance", True),
    "CUSIP": ("Cross-system identifier linking finance records to a security or instrument.", "Certified", "Finance", True),
    "VENDOR_ID": ("Unique identifier for a vendor.", "", "Finance", True),
    "INVOICE_DATE": ("Date the invoice was issued.", "", "Finance", False),
    "AMOUNT": ("Invoice amount due, in USD.", "Certified", "Finance", False),
    "PAYMENT_ID": ("Unique identifier for a payment record.", "", "Finance", False),
    "PAYMENT_DATE": ("Date the payment was made.", "", "Finance", False),
    "AMOUNT_PAID": ("Amount paid against the invoice, in USD.", "", "Finance", False),
    "VENDOR_NAME": ("Legal name of the vendor.", "", "Finance", False),
    "TAX_ID": ("Vendor's tax identification number.", "PII", "Finance", False),
}

# Synthetic usage: (column_name, table, consumer_name, consumer_type,
# days_ago, query_count). Only references (column, table) pairs that exist
# in TABLES. CUSIP and CUSTOMER_ID are deliberately load-bearing (many
# consumers across all 5 types, recent last_used). Several documented
# columns (FIRST_NAME, LAST_NAME, EMAIL, HIRE_DATE, DEPARTMENT_NAME,
# PRODUCT_NAME, GROSS_PAY, NET_PAY, ...) intentionally have NO usage rows at
# all, so the empty state is visible in the demo.
USAGE_ROWS = [
    # CUSIP — load-bearing: all 5 consumer types, spread of recency
    ("CUSIP", "FINANCE_DB.PUBLIC.INVOICES", "finance_dashboard", "Dashboard", 5, 1200),
    ("CUSIP", "FINANCE_DB.REPORTING.GL_ENTRIES", "gl_reconciliation", "dbt model", 2, 340),
    ("CUSIP", "FINANCE_DB.PUBLIC.PAYMENTS", "audit_report_app", "Streamlit app", 10, 89),
    ("CUSIP", "FINANCE_DB.PUBLIC.INVOICES", "nightly_recon_job", "Scheduled query", 1, 5000),
    ("CUSIP", "FINANCE_DB.PUBLIC.VENDORS", "jsmith", "User / ad-hoc", 45, 12),

    # CUSTOMER_ID — load-bearing: high query counts, very recent
    ("CUSTOMER_ID", "SALES_DB.PUBLIC.CUSTOMERS", "customer_360_app", "Streamlit app", 1, 8500),
    ("CUSTOMER_ID", "SALES_DB.PUBLIC.ORDERS", "stg_customers", "dbt model", 1, 220),
    ("CUSTOMER_ID", "SALES_DB.PUBLIC.CUSTOMERS", "sales_dashboard", "Dashboard", 3, 640),
    ("CUSTOMER_ID", "SALES_DB.ANALYTICS.SALES_SUMMARY", "marketing_ops_job", "Scheduled query", 7, 150),

    # Moderate — a couple of consumers each
    ("EMPLOYEE_ID", "HR_DB.PUBLIC.EMPLOYEES", "hr_portal", "Streamlit app", 14, 320),
    ("EMPLOYEE_ID", "HR_DB.PUBLIC.PAYROLL", "payroll_dbt", "dbt model", 2, 95),
    ("ORDER_ID", "SALES_DB.PUBLIC.ORDERS", "order_tracking_app", "Streamlit app", 4, 2100),
    ("ORDER_ID", "SALES_DB.PUBLIC.ORDER_ITEMS", "fulfillment_dashboard", "Dashboard", 6, 780),
    ("INVOICE_ID", "FINANCE_DB.PUBLIC.INVOICES", "ap_dashboard", "Dashboard", 3, 560),
    ("INVOICE_ID", "FINANCE_DB.PUBLIC.INVOICES", "vendor_dbt_model", "dbt model", 1, 140),

    # Single consumer
    ("SSN", "HR_DB.PUBLIC.EMPLOYEES", "compliance_audit_job", "Scheduled query", 60, 20),
    ("TOTAL_AMOUNT", "SALES_DB.PUBLIC.ORDERS", "finance_dashboard", "Dashboard", 5, 450),
    ("VENDOR_ID", "FINANCE_DB.PUBLIC.VENDORS", "ap_dashboard", "Dashboard", 8, 75),
    ("PRODUCT_ID", "SALES_DB.PUBLIC.PRODUCTS", "catalog_app", "Streamlit app", 12, 410),
    ("DEPARTMENT_ID", "HR_DB.PUBLIC.DEPARTMENTS", "hr_portal", "Streamlit app", 20, 60),

    # Single consumer, very stale (~9 months) — for a later "still used?" view
    ("AMOUNT", "FINANCE_DB.PUBLIC.INVOICES", "old_reporting_tool", "User / ad-hoc", 270, 8),
]


def build_structure_df() -> pd.DataFrame:
    rows = []
    for (db, schema, table), columns in TABLES.items():
        for col in columns:
            rows.append({
                "TABLE_CATALOG": db,
                "TABLE_SCHEMA": schema,
                "TABLE_NAME": table,
                "COLUMN_NAME": col,
                "DATA_TYPE": DATA_TYPES[col],
            })
    return pd.DataFrame(rows)


def build_descriptions_df() -> pd.DataFrame:
    rows = []
    for col, (desc, tags, steward, approved) in sorted(DESCRIPTIONS.items()):
        rows.append({
            "Column Name": col,
            "Description": desc,
            "Tags": tags,
            "Steward": steward,
            "Approved": "TRUE" if approved else "FALSE",
        })
    return pd.DataFrame(rows)


# People available to assign columns to — mirrors config.WORKFLOW_ASSIGNEES.
WORKFLOW_ASSIGNEES = ["Priya", "Deepak", "Marcus", "Elena"]

# Structural columns deliberately left OUT of assignments.csv entirely, so
# the Documentation workspace page's live auto-seed/reconcile step has real
# work to do on first load instead of finding every column already tracked.
OMITTED_FROM_ASSIGNMENTS = {"ZIP_CODE", "SHIPPING_ADDRESS", "LAST_SCORED_AT", "POSTED_AT"}


def _column_index() -> dict:
    """column_name -> (table_count, comma-joined sorted unique databases)."""
    per_col_tables: dict = {}
    for (db, schema, table), columns in TABLES.items():
        for col in columns:
            per_col_tables.setdefault(col, set()).add((db, schema, table))
    return {
        col: (len(tbls), ", ".join(sorted({db for db, _, _ in tbls})))
        for col, tbls in per_col_tables.items()
    }


def build_assignments_df() -> pd.DataFrame:
    col_index = _column_index()
    distinct_cols = sorted(col_index)
    rows = []

    # Columns already documented in DESCRIPTIONS — approved ones map
    # straight to status "Approved"; the rest ("has a draft, not yet
    # signed off") alternate Submitted / In progress for a realistic split.
    documented_cols = [c for c in distinct_cols if c in DESCRIPTIONS]
    for i, col in enumerate(documented_cols):
        desc, _tags, _steward, approved = DESCRIPTIONS[col]
        table_count, data_product = col_index[col]
        assignee = WORKFLOW_ASSIGNEES[i % len(WORKFLOW_ASSIGNEES)]
        if approved:
            status = "Approved"
        else:
            status = "Submitted" if i % 2 == 0 else "In progress"
        rows.append({
            "column_name": col, "data_product": data_product, "table_count": table_count,
            "description": desc, "assigned_to": assignee, "status": status,
            "origin": "structure", "orphaned": False,
            "updated_by": assignee, "updated_at": _days_ago(5 + i % 60),
        })

    # Undocumented columns — a realistic spread of Unassigned / Assigned
    # (claimed, description not started) / In progress (claimed, partial
    # draft). A handful are skipped entirely (OMITTED_FROM_ASSIGNMENTS).
    undocumented_cols = [
        c for c in distinct_cols if c not in DESCRIPTIONS and c not in OMITTED_FROM_ASSIGNMENTS
    ]
    for i, col in enumerate(undocumented_cols):
        table_count, data_product = col_index[col]
        bucket = i % 3
        if bucket == 0:
            status, assignee, desc = "Unassigned", "", ""
        elif bucket == 1:
            status, assignee, desc = "Assigned", WORKFLOW_ASSIGNEES[i % len(WORKFLOW_ASSIGNEES)], ""
        else:
            assignee = WORKFLOW_ASSIGNEES[i % len(WORKFLOW_ASSIGNEES)]
            status, desc = "In progress", f"Draft: {col.replace('_', ' ').title()} — needs review."
        rows.append({
            "column_name": col, "data_product": data_product, "table_count": table_count,
            "description": desc, "assigned_to": assignee, "status": status,
            "origin": "structure", "orphaned": False,
            "updated_by": assignee, "updated_at": _days_ago(2 + i % 30) if assignee else "",
        })

    # Manual row — a business-glossary term with no physical column, added
    # straight by a coordinator.
    rows.append({
        "column_name": "NET_REVENUE_MARGIN", "data_product": "FINANCE_DB", "table_count": 0,
        "description": (
            "Business-defined ratio of net revenue to gross revenue, used in "
            "board reporting. Not a physical column — defined here for the glossary."
        ),
        "assigned_to": "Priya", "status": "Submitted", "origin": "manual", "orphaned": False,
        "updated_by": "Priya", "updated_at": _days_ago(10),
    })

    # Orphaned row — references a column no longer present in structure.csv
    # (superseded), kept rather than deleted so the written description isn't lost.
    rows.append({
        "column_name": "LEGACY_ACCOUNT_CODE", "data_product": "FINANCE_DB", "table_count": 1,
        "description": "Legacy GL account code, superseded by ACCOUNT_CODE.",
        "assigned_to": "Marcus", "status": "Approved", "origin": "structure", "orphaned": True,
        "updated_by": "Marcus", "updated_at": _days_ago(200),
    })

    return pd.DataFrame(rows, columns=[
        "column_name", "data_product", "table_count", "description", "assigned_to",
        "status", "origin", "orphaned", "updated_by", "updated_at",
    ])


# A handful of columns get a "live" (query-sourced) description, distinct
# in wording from DESCRIPTIONS' curated text — so the workspace table's
# curated-vs-live columns visibly diverge for the same column_name rather
# than just duplicating each other. Most columns get no live description at
# all (query comments are often sparser than a curated glossary).
LIVE_DESCRIPTIONS = {
    "CUSTOMER_ID": "Warehouse comment: surrogate key, customers table.",
    "CUSIP": "Warehouse comment: 9-char security identifier.",
    "ORDER_ID": "Warehouse comment: order surrogate key.",
    "EMPLOYEE_ID": "Warehouse comment: HR system employee key.",
    "INVOICE_ID": "Warehouse comment: AP invoice surrogate key.",
    "EMAIL": "Warehouse comment: contact email, unvalidated.",
    "STATUS": "Warehouse comment: free-text lifecycle state.",
    "CREATED_AT": "Warehouse comment: row insert timestamp (UTC).",
}


def build_workspace_query_df() -> pd.DataFrame:
    """Source 1 for the Documentation workspace table — a live
    structure+description query shaped as QUALIFIED_OBJECT_NAME (not
    separate database/schema/table columns), mirroring how a real
    warehouse query actually returns it. Built from the same TABLES dict
    as structure.csv, so N-tables/data-product counts stay consistent with
    the rest of the demo (CUSIP/CUSTOMER_ID etc. are already multi-table)."""
    rows = []
    for (db, schema, table), columns in TABLES.items():
        qualified = f"{db}.{schema}.{table}"
        for position, col in enumerate(columns, start=1):
            rows.append({
                "QUALIFIED_OBJECT_NAME": qualified,
                "COLUMN_NAME": col,
                "ORDINAL_POSITION": position,
                "DESCRIPTION": LIVE_DESCRIPTIONS.get(col, ""),
            })
    return pd.DataFrame(rows)


def build_workspace_curated_df() -> pd.DataFrame:
    """Source 2 for the Documentation workspace table — an independently
    curated descriptions/approval feed, distinct from the workflow table.
    Reuses the same DESCRIPTIONS dict descriptions.csv is built from (partial
    coverage by design — some columns curated, some not), repackaged into
    this source's own column_name/description/approved shape."""
    rows = []
    for col, (desc, _tags, _steward, approved) in sorted(DESCRIPTIONS.items()):
        rows.append({
            "column_name": col,
            "description": desc,
            "approved": "TRUE" if approved else "FALSE",
        })
    return pd.DataFrame(rows)


def build_usage_df() -> pd.DataFrame:
    rows = []
    for col, table, consumer_name, consumer_type, days_ago, query_count in USAGE_ROWS:
        rows.append({
            "column_name": col,
            "table": table,
            "consumer_name": consumer_name,
            "consumer_type": consumer_type,
            "last_used": _days_ago(days_ago),
            "query_count": query_count,
        })
    return pd.DataFrame(rows)


def main():
    structure_df = build_structure_df()
    descriptions_df = build_descriptions_df()
    usage_df = build_usage_df()
    assignments_df = build_assignments_df()
    workspace_query_df = build_workspace_query_df()
    workspace_curated_df = build_workspace_curated_df()

    distinct_cols = {col for cols in TABLES.values() for col in cols}
    n_dbs = len({db for db, _, _ in TABLES})
    n_schemas = len({(db, s) for db, s, _ in TABLES})
    n_tables = len(TABLES)

    assert n_dbs >= 3, "need >= 3 databases"
    assert n_schemas >= 4, "need >= 4 schemas"
    assert n_tables >= 12, "need >= 12 tables"
    assert len(structure_df) >= 50, "need >= 50 physical columns"

    usage_consumer_types = {row[3] for row in USAGE_ROWS}
    usage_cols = {row[0] for row in USAGE_ROWS}
    assert len(usage_consumer_types) >= 5, "need all 5 consumer types represented"
    assert usage_cols <= distinct_cols, "usage.csv references a column not in structure.csv"

    assignment_statuses = set(assignments_df["status"])
    approved_pct = (assignments_df["status"] == "Approved").mean() * 100
    assert {"Unassigned", "Assigned", "In progress", "Submitted", "Approved"} <= assignment_statuses
    assert approved_pct < 100, "assignments.csv coverage must be < 100% for the metrics to be meaningful"
    assert (assignments_df["origin"] == "manual").sum() >= 1, "need >= 1 manual row"
    assert (assignments_df["orphaned"]).sum() >= 1, "need >= 1 orphaned row"
    assigned_cols = set(assignments_df["column_name"]) - {"NET_REVENUE_MARGIN", "LEGACY_ACCOUNT_CODE"}
    assert assigned_cols <= distinct_cols, "assignments.csv references a column not in structure.csv"
    assert OMITTED_FROM_ASSIGNMENTS & distinct_cols == OMITTED_FROM_ASSIGNMENTS, (
        "OMITTED_FROM_ASSIGNMENTS must reference real structural columns"
    )
    assert distinct_cols - assigned_cols == OMITTED_FROM_ASSIGNMENTS, (
        "every structural column must be either assigned or deliberately omitted"
    )

    workspace_query_tables_by_col: dict = {}
    for _, r in workspace_query_df.iterrows():
        workspace_query_tables_by_col.setdefault(r["COLUMN_NAME"], set()).add(r["QUALIFIED_OBJECT_NAME"])
    multi_table_cols = {c for c, tbls in workspace_query_tables_by_col.items() if len(tbls) > 1}
    assert len(multi_table_cols) >= 2, "need >= 2 columns spanning multiple tables in workspace_query.csv"
    multi_product_cols = {
        c for c, tbls in workspace_query_tables_by_col.items()
        if len({t.split(".")[0] for t in tbls}) > 1
    }
    assert len(multi_product_cols) >= 1, "need >= 1 column spanning multiple data products in workspace_query.csv"
    assert 0 < len(workspace_curated_df) < len(distinct_cols), (
        "workspace_curated.csv must cover some but not all columns"
    )

    structure_path = os.path.join(HERE, "structure.csv")
    descriptions_path = os.path.join(HERE, "descriptions.csv")
    usage_path = os.path.join(HERE, "usage.csv")
    assignments_path = os.path.join(HERE, "assignments.csv")
    workspace_query_path = os.path.join(HERE, "workspace_query.csv")
    workspace_curated_path = os.path.join(HERE, "workspace_curated.csv")

    structure_df.to_csv(structure_path, index=False)
    descriptions_df.to_csv(descriptions_path, index=False)
    usage_df.to_csv(usage_path, index=False)
    assignments_df.to_csv(assignments_path, index=False)
    workspace_query_df.to_csv(workspace_query_path, index=False)
    workspace_curated_df.to_csv(workspace_curated_path, index=False)

    print(f"Wrote {structure_path} ({len(structure_df)} rows, "
          f"{n_dbs} databases, {n_schemas} schemas, {n_tables} tables, "
          f"{len(distinct_cols)} distinct column names)")
    print(f"Wrote {descriptions_path} ({len(descriptions_df)} documented "
          f"columns of {len(distinct_cols)} distinct — "
          f"{len(distinct_cols) - len(descriptions_df)} left undocumented)")
    print(f"Wrote {usage_path} ({len(usage_df)} usage rows across "
          f"{len(usage_cols)} columns, {len(usage_consumer_types)} consumer types)")
    print(f"Wrote {assignments_path} ({len(assignments_df)} rows, "
          f"{approved_pct:.0f}% approved, {len(OMITTED_FROM_ASSIGNMENTS)} columns "
          f"omitted for live auto-seed demo)")
    print(f"Wrote {workspace_query_path} ({len(workspace_query_df)} rows, "
          f"{len(multi_table_cols)} columns spanning multiple tables, "
          f"{len(multi_product_cols)} spanning multiple data products)")
    print(f"Wrote {workspace_curated_path} ({len(workspace_curated_df)} curated "
          f"columns of {len(distinct_cols)} distinct)")


if __name__ == "__main__":
    main()
