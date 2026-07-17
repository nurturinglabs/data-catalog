"""
Regenerates the two synthetic demo sources: structure.csv and
descriptions.xlsx. Run with: python sample_data/_generate.py

structure.csv is INFORMATION_SCHEMA-shaped physical schema for 3 synthetic
databases. descriptions.xlsx is a partial, human-authored description layer
covering roughly two-thirds of the distinct column names, so the demo shows a
non-trivial reverse index and coverage < 100%.
"""

import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

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

# Curated descriptions: column_name -> (description, tags, steward).
# Roughly two-thirds of distinct column names are documented; the rest are
# left out on purpose so coverage < 100%.
DESCRIPTIONS = {
    "CUSTOMER_ID": ("Unique identifier for a customer account.", "Certified", "Data Governance"),
    "FIRST_NAME": ("Given name of the individual.", "PII", "Data Governance"),
    "LAST_NAME": ("Family name of the individual.", "PII", "Data Governance"),
    "EMAIL": ("Primary email address on file.", "PII", "Data Governance"),
    "PHONE": ("Primary phone number on file.", "PII", "Data Governance"),
    "CITY": ("City component of the mailing address.", "", "Data Governance"),
    "STATE": ("Two-letter US state code.", "", "Data Governance"),
    "CREATED_AT": ("Timestamp the record was first created.", "", ""),
    "ORDER_ID": ("Unique identifier for a customer order.", "Certified", "Sales Ops"),
    "ORDER_DATE": ("Calendar date the order was placed.", "", "Sales Ops"),
    "STATUS": ("Current lifecycle status of the record (e.g. OPEN, CLOSED).", "", "Sales Ops"),
    "TOTAL_AMOUNT": ("Total order value in USD, including tax.", "Certified", "Sales Ops"),
    "ORDER_ITEM_ID": ("Unique identifier for a single line item on an order.", "", "Sales Ops"),
    "PRODUCT_ID": ("Unique identifier for a product SKU.", "Certified", "Sales Ops"),
    "QUANTITY": ("Number of units ordered for this line item.", "", ""),
    "UNIT_PRICE": ("List price per unit at time of order, in USD.", "", "Sales Ops"),
    "PRODUCT_NAME": ("Human-readable product name.", "", "Sales Ops"),
    "CATEGORY": ("Product category used for merchandising and reporting.", "", ""),
    "SEGMENT": ("Marketing-assigned customer segment label.", "", "Marketing Analytics"),
    "LIFETIME_VALUE": ("Modeled lifetime value of the customer, in USD.", "", "Marketing Analytics"),
    "EMPLOYEE_ID": ("Unique identifier for an employee record.", "Certified", "People Analytics"),
    "HIRE_DATE": ("Date the employee's current employment began.", "", "People Analytics"),
    "DEPARTMENT_ID": ("Unique identifier for an organizational department.", "", "People Analytics"),
    "MANAGER_ID": ("Employee ID of this employee's direct manager.", "", "People Analytics"),
    "SSN": ("Social Security Number. Restricted access.", "PII", "People Analytics"),
    "DEPARTMENT_NAME": ("Display name of the department.", "", "People Analytics"),
    "PAYROLL_ID": ("Unique identifier for a payroll run line.", "", "People Analytics"),
    "PAY_PERIOD": ("Pay period the payroll entry applies to (YYYY-MM).", "", ""),
    "GROSS_PAY": ("Gross pay before deductions, in USD.", "", "People Analytics"),
    "NET_PAY": ("Net pay after deductions, in USD.", "", "People Analytics"),
    "INVOICE_ID": ("Unique identifier for a vendor invoice.", "Certified", "Finance"),
    "CUSIP": ("Cross-system identifier linking finance records to a security or instrument.", "Certified", "Finance"),
    "VENDOR_ID": ("Unique identifier for a vendor.", "", "Finance"),
    "INVOICE_DATE": ("Date the invoice was issued.", "", "Finance"),
    "AMOUNT": ("Invoice amount due, in USD.", "Certified", "Finance"),
    "PAYMENT_ID": ("Unique identifier for a payment record.", "", "Finance"),
    "PAYMENT_DATE": ("Date the payment was made.", "", "Finance"),
    "AMOUNT_PAID": ("Amount paid against the invoice, in USD.", "", "Finance"),
    "VENDOR_NAME": ("Legal name of the vendor.", "", "Finance"),
    "TAX_ID": ("Vendor's tax identification number.", "PII", "Finance"),
}


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
    for col, (desc, tags, steward) in sorted(DESCRIPTIONS.items()):
        rows.append({
            "Column Name": col,
            "Description": desc,
            "Tags": tags,
            "Steward": steward,
        })
    return pd.DataFrame(rows)


def main():
    structure_df = build_structure_df()
    descriptions_df = build_descriptions_df()

    distinct_cols = {col for cols in TABLES.values() for col in cols}
    n_dbs = len({db for db, _, _ in TABLES})
    n_schemas = len({(db, s) for db, s, _ in TABLES})
    n_tables = len(TABLES)

    assert n_dbs >= 3, "need >= 3 databases"
    assert n_schemas >= 4, "need >= 4 schemas"
    assert n_tables >= 12, "need >= 12 tables"
    assert len(structure_df) >= 50, "need >= 50 physical columns"

    structure_path = os.path.join(HERE, "structure.csv")
    descriptions_path = os.path.join(HERE, "descriptions.xlsx")

    structure_df.to_csv(structure_path, index=False)
    descriptions_df.to_excel(descriptions_path, index=False, sheet_name="Sheet1")

    print(f"Wrote {structure_path} ({len(structure_df)} rows, "
          f"{n_dbs} databases, {n_schemas} schemas, {n_tables} tables, "
          f"{len(distinct_cols)} distinct column names)")
    print(f"Wrote {descriptions_path} ({len(descriptions_df)} documented "
          f"columns of {len(distinct_cols)} distinct — "
          f"{len(distinct_cols) - len(descriptions_df)} left undocumented)")


if __name__ == "__main__":
    main()
