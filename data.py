"""
data.py — the seam. Two-layer load + join + validation.

Public surface: `load_catalog()`, `load_health()`, `CANONICAL_FIELDS`.
Everything else is private. This module must never reference a concrete data
source, path, table name, or credential — all of that lives in config.py.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections import Counter

import pandas as pd

import config

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


CANONICAL_FIELDS = [
    "column_name",
    "description",
    "tags",
    "steward",
    "approved",
    "data_type",
    "tables",
    "databases",
    "schemas",
    "documented",
]

_NULL_TOKENS = {"nan", "none", "null"}
_TRUTHY_TOKENS = {"true", "yes", "y", "1", "approved", "x"}

_last_health: dict = {}


class DataSourceError(Exception):
    """Raised when a configured data source cannot be reached or read."""


# ─────────────────────────────────────────────────────────────────────────────
# Cleaning helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return ""
    return text


def _split_list(value, delimiter: str) -> list[str]:
    cleaned = _clean_cell(value)
    if not cleaned:
        return []
    return [part.strip() for part in cleaned.split(delimiter) if part.strip()]


def _parse_bool(value) -> bool:
    """Truthy on common spreadsheet conventions: TRUE/YES/Y/1/APPROVED/X
    (case-insensitive). Anything else, including blank/nan, is False."""
    return _clean_cell(value).strip().lower() in _TRUTHY_TOKENS


def _ci_header_lookup(columns) -> dict[str, str]:
    """Map lowercased header -> actual header, for case-insensitive lookup."""
    return {str(c).strip().lower(): c for c in columns}


# ─────────────────────────────────────────────────────────────────────────────
# Validation (§8.2)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_headers(
    raw_df: pd.DataFrame,
    field_map: dict,
    required_fields: list[str],
    optional_fields: list[str],
    source_label: str,
) -> dict:
    """
    Verify required mapped headers exist (case-insensitively) in raw_df.
    Raises ValueError naming the source, canonical field, expected header,
    and the headers actually present if a required one is missing.
    Returns a health fragment: headers found/missing per field.
    """
    ci_lookup = _ci_header_lookup(raw_df.columns)

    found: dict = {}
    missing_required: list[tuple[str, str]] = []
    missing_optional: list[str] = []

    for field in required_fields:
        header = field_map.get(field)
        actual = ci_lookup.get(str(header).strip().lower()) if header else None
        if actual is None:
            missing_required.append((field, header))
        else:
            found[field] = actual

    for field in optional_fields:
        header = field_map.get(field)
        actual = ci_lookup.get(str(header).strip().lower()) if header else None
        if actual is None:
            missing_optional.append(field)
        else:
            found[field] = actual

    if missing_required:
        detail = ", ".join(
            f"canonical field '{field}' expected header '{header}'"
            for field, header in missing_required
        )
        raise ValueError(
            f"[{source_label}] missing required header(s): {detail}. "
            f"Columns present: {list(raw_df.columns)}"
        )

    return {
        "headers_found": found,
        "headers_missing_optional": missing_optional,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Readers — one per source type. Each returns a raw DataFrame with original
# headers untouched. Snowflake session obtained lazily so the app runs
# locally with no Snowflake libraries installed.
# ─────────────────────────────────────────────────────────────────────────────

def _read_csv_local_descriptions() -> pd.DataFrame:
    cfg = config.DESC_CSV_LOCAL
    try:
        return pd.read_csv(cfg["path"])
    except Exception as exc:
        raise DataSourceError(f"Could not read local CSV '{cfg['path']}': {exc}") from exc


def _read_excel_local() -> pd.DataFrame:
    cfg = config.DESC_EXCEL_LOCAL
    try:
        return pd.read_excel(cfg["path"], sheet_name=cfg.get("sheet", 0))
    except Exception as exc:
        raise DataSourceError(f"Could not read local Excel '{cfg['path']}': {exc}") from exc


def _read_excel_stage() -> pd.DataFrame:
    cfg = config.DESC_EXCEL_STAGE
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        local_path = session.file.get(cfg["stage_path"], "/tmp")[0].file
        return pd.read_excel(local_path, sheet_name=cfg.get("sheet", 0))
    except Exception as exc:
        raise DataSourceError(
            f"Could not read staged Excel '{cfg['stage_path']}': {exc}"
        ) from exc


def _read_descriptions_snowflake_table() -> pd.DataFrame:
    cfg = config.DESC_SNOWFLAKE_TABLE
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.table(cfg["table"]).to_pandas()
    except Exception as exc:
        raise DataSourceError(f"Could not read table '{cfg['table']}': {exc}") from exc


def _build_information_schema_query() -> str:
    query = config.STRUCTURE_QUERY.strip()
    if config.DATABASE_ALLOWLIST:
        in_list = ", ".join(f"'{db}'" for db in config.DATABASE_ALLOWLIST)
        query += f"\n  AND TABLE_CATALOG IN ({in_list})"
    return query


def _read_information_schema() -> pd.DataFrame:
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        query = _build_information_schema_query()
        return session.sql(query).to_pandas()
    except Exception as exc:
        raise DataSourceError(f"Could not query structure source: {exc}") from exc


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_database_identifier(name: str) -> None:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"STRUCTURE_DATABASES contains an invalid database name: {name!r}. "
            f"Each entry must be a plain identifier (letters, digits, underscore)."
        )


def _build_information_schema_union_query() -> str:
    databases = list(config.STRUCTURE_DATABASES)
    if not databases:
        raise ValueError(
            "STRUCTURE_DATABASES is empty. Populate it with the databases to pull "
            "structure from when STRUCTURE_SOURCE is 'information_schema_union'."
        )
    for db in databases:
        _validate_database_identifier(db)

    if config.DATABASE_ALLOWLIST:
        databases = [db for db in databases if db in config.DATABASE_ALLOWLIST]
        if not databases:
            raise ValueError(
                "DATABASE_ALLOWLIST excludes every database in STRUCTURE_DATABASES; "
                "there is nothing left to query."
            )

    selects = [
        "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        f"FROM {db}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA <> 'INFORMATION_SCHEMA'"
        for db in databases
    ]
    return "\nUNION ALL\n".join(selects)


def _read_information_schema_union() -> pd.DataFrame:
    query = _build_information_schema_union_query()
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.sql(query).to_pandas()
    except Exception as exc:
        raise DataSourceError(f"Could not query structure source: {exc}") from exc


def _read_local_csv() -> pd.DataFrame:
    cfg = config.STRUCT_LOCAL_CSV
    try:
        df = pd.read_csv(cfg["path"])
    except Exception as exc:
        raise DataSourceError(f"Could not read local CSV '{cfg['path']}': {exc}") from exc
    return _apply_allowlist_pandas(df)


def _read_snapshot_table() -> pd.DataFrame:
    cfg = config.STRUCT_SNAPSHOT_TABLE
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        df = session.table(cfg["table"]).to_pandas()
    except Exception as exc:
        raise DataSourceError(f"Could not read table '{cfg['table']}': {exc}") from exc
    return _apply_allowlist_pandas(df)


def _apply_allowlist_pandas(df: pd.DataFrame) -> pd.DataFrame:
    """Filter a raw structure DataFrame to DATABASE_ALLOWLIST (§8.3)."""
    if not config.DATABASE_ALLOWLIST:
        return df
    ci_lookup = _ci_header_lookup(df.columns)
    db_header = ci_lookup.get(str(config.STRUCTURE_MAP["database"]).strip().lower())
    if db_header is None:
        return df
    return df[df[db_header].astype(str).isin(config.DATABASE_ALLOWLIST)]


def _read_raw_descriptions() -> pd.DataFrame:
    if config.DESCRIPTIONS_SOURCE == "csv_local":
        return _read_csv_local_descriptions()
    if config.DESCRIPTIONS_SOURCE == "excel_local":
        return _read_excel_local()
    if config.DESCRIPTIONS_SOURCE == "excel_stage":
        return _read_excel_stage()
    if config.DESCRIPTIONS_SOURCE == "snowflake_table":
        return _read_descriptions_snowflake_table()
    raise DataSourceError(f"Unknown DESCRIPTIONS_SOURCE: {config.DESCRIPTIONS_SOURCE!r}")


def _read_raw_structure() -> pd.DataFrame:
    if config.STRUCTURE_SOURCE == "information_schema":
        return _read_information_schema()
    if config.STRUCTURE_SOURCE == "information_schema_union":
        return _read_information_schema_union()
    if config.STRUCTURE_SOURCE == "local_csv":
        return _read_local_csv()
    if config.STRUCTURE_SOURCE == "snapshot_table":
        return _read_snapshot_table()
    raise DataSourceError(f"Unknown STRUCTURE_SOURCE: {config.STRUCTURE_SOURCE!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Cleaners — canonicalize raw frames to canonical column names
# ─────────────────────────────────────────────────────────────────────────────

def _canonicalize_descriptions(raw_df: pd.DataFrame, headers_found: dict) -> pd.DataFrame:
    out = pd.DataFrame()
    out["column_name"] = raw_df[headers_found["column_name"]].map(_clean_cell)
    out["description"] = raw_df[headers_found["description"]].map(_clean_cell)
    if "tags" in headers_found:
        out["tags"] = raw_df[headers_found["tags"]].map(
            lambda v: _split_list(v, config.TAGS_DELIMITER)
        )
    else:
        out["tags"] = [[] for _ in range(len(out))]
    if "steward" in headers_found:
        out["steward"] = raw_df[headers_found["steward"]].map(_clean_cell)
    else:
        out["steward"] = ""
    if "approved" in headers_found:
        out["approved"] = raw_df[headers_found["approved"]].map(_parse_bool)
    else:
        out["approved"] = False
    # Drop rows with no column name — nothing to key a join on.
    out = out[out["column_name"] != ""]
    return out


def _canonicalize_structure(raw_df: pd.DataFrame, headers_found: dict) -> pd.DataFrame:
    out = pd.DataFrame()
    out["database"] = raw_df[headers_found["database"]].map(_clean_cell)
    out["schema"] = raw_df[headers_found["schema"]].map(_clean_cell)
    out["table"] = raw_df[headers_found["table"]].map(_clean_cell)
    out["column_name"] = raw_df[headers_found["column_name"]].map(_clean_cell)
    out["data_type"] = raw_df[headers_found["data_type"]].map(_clean_cell)
    out = out[
        (out["column_name"] != "") & (out["table"] != "") & (out["schema"] != "")
    ]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Structure collapse — group physical columns to JOIN_GRAIN
# ─────────────────────────────────────────────────────────────────────────────

def _grain_key(row) -> str:
    grain = config.JOIN_GRAIN
    if grain == "column_name":
        return row["column_name"]
    if grain == "schema.column":
        return f"{row['database']}.{row['schema']}.{row['column_name']}"
    if grain == "table.column":
        return f"{row['database']}.{row['schema']}.{row['table']}.{row['column_name']}"
    raise ValueError(f"Unknown JOIN_GRAIN: {grain!r}")


def _collapse_structure(structure_df: pd.DataFrame) -> pd.DataFrame:
    if structure_df.empty:
        return pd.DataFrame(
            columns=["column_name", "data_type", "tables", "databases", "schemas"]
        )

    df = structure_df.copy()
    df["_grain_key"] = df.apply(_grain_key, axis=1)
    df["_table_fqn"] = df["database"] + "." + df["schema"] + "." + df["table"]
    df["_schema_fqn"] = df["database"] + "." + df["schema"]

    rows = []
    for key, group in df.groupby("_grain_key", sort=True):
        data_type = Counter(group["data_type"]).most_common(1)[0][0]
        rows.append({
            "column_name": group["column_name"].iloc[0],
            "data_type": data_type,
            "tables": sorted(group["_table_fqn"].unique().tolist()),
            "databases": sorted(group["database"].unique().tolist()),
            "schemas": sorted(group["_schema_fqn"].unique().tolist()),
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Join + spine
# ─────────────────────────────────────────────────────────────────────────────

def _join(collapsed_structure: pd.DataFrame, descriptions_df: pd.DataFrame) -> pd.DataFrame:
    desc_lookup: dict[str, dict] = {}
    for _, row in descriptions_df.iterrows():
        desc_lookup[row["column_name"].upper()] = {
            "description": row["description"],
            "tags": row["tags"],
            "steward": row["steward"],
            "approved": row["approved"],
        }

    records = []
    for _, row in collapsed_structure.iterrows():
        match = desc_lookup.get(row["column_name"].upper())
        description = match["description"] if match else ""
        tags = match["tags"] if match else []
        steward = match["steward"] if match else ""
        approved = match["approved"] if match else False
        records.append({
            "column_name": row["column_name"],
            "description": description,
            "tags": tags,
            "steward": steward,
            "approved": approved,
            "data_type": row["data_type"],
            "tables": row["tables"],
            "databases": row["databases"],
            "schemas": row["schemas"],
            "documented": bool(description),
        })

    return pd.DataFrame(records, columns=CANONICAL_FIELDS)


def _apply_spine(catalog_df: pd.DataFrame) -> pd.DataFrame:
    if config.CATALOG_SPINE == "descriptions":
        return catalog_df[catalog_df["documented"]].reset_index(drop=True)
    return catalog_df.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Build — the full pipeline, uncached (tests call this directly)
# ─────────────────────────────────────────────────────────────────────────────

def _build_catalog_and_health() -> tuple[pd.DataFrame, dict]:
    raw_descriptions = _read_raw_descriptions()
    desc_validation = _validate_headers(
        raw_descriptions,
        config.DESCRIPTION_MAP,
        required_fields=["column_name", "description"],
        optional_fields=["tags", "steward", "approved"],
        source_label=f"descriptions:{config.DESCRIPTIONS_SOURCE}",
    )
    descriptions_df = _canonicalize_descriptions(
        raw_descriptions, desc_validation["headers_found"]
    )

    raw_structure = _read_raw_structure()
    struct_validation = _validate_headers(
        raw_structure,
        config.STRUCTURE_MAP,
        required_fields=["database", "schema", "table", "column_name", "data_type"],
        optional_fields=[],
        source_label=f"structure:{config.STRUCTURE_SOURCE}",
    )

    structure_truncated = False
    if len(raw_structure) > config.MAX_STRUCTURE_ROWS:
        raw_structure = raw_structure.iloc[: config.MAX_STRUCTURE_ROWS]
        structure_truncated = True

    structure_df = _canonicalize_structure(raw_structure, struct_validation["headers_found"])
    collapsed = _collapse_structure(structure_df)
    catalog_df = _join(collapsed, descriptions_df)
    catalog_df = _apply_spine(catalog_df)

    assert list(catalog_df.columns) == CANONICAL_FIELDS, (
        f"load_catalog() output columns {list(catalog_df.columns)} "
        f"!= CANONICAL_FIELDS {CANONICAL_FIELDS}"
    )

    entry_count = len(catalog_df)
    documented_count = int(catalog_df["documented"].sum())
    coverage_pct = (documented_count / entry_count * 100) if entry_count else 0.0

    health = {
        "descriptions_source": config.DESCRIPTIONS_SOURCE,
        "structure_source": config.STRUCTURE_SOURCE,
        "descriptions_row_count": len(descriptions_df),
        "structure_row_count": len(structure_df),
        "structure_truncated": structure_truncated,
        "max_structure_rows": config.MAX_STRUCTURE_ROWS,
        "join_grain": config.JOIN_GRAIN,
        "catalog_spine": config.CATALOG_SPINE,
        "entry_count": entry_count,
        "documented_count": documented_count,
        "coverage_pct": coverage_pct,
        "descriptions_headers_found": desc_validation["headers_found"],
        "descriptions_headers_missing_optional": desc_validation["headers_missing_optional"],
        "structure_headers_found": struct_validation["headers_found"],
        "database_allowlist": list(config.DATABASE_ALLOWLIST),
        "last_refresh": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    return catalog_df, health


def _load_catalog_impl() -> pd.DataFrame:
    catalog_df, health = _build_catalog_and_health()
    _last_health.clear()
    _last_health.update(health)
    return catalog_df


# ─────────────────────────────────────────────────────────────────────────────
# Public surface
# ─────────────────────────────────────────────────────────────────────────────

if _HAS_STREAMLIT:
    load_catalog = st.cache_data(ttl=config.CACHE_TTL_SECONDS)(_load_catalog_impl)
else:
    load_catalog = _load_catalog_impl


def load_health() -> dict:
    """Health report from the most recent load_catalog() call."""
    if not _last_health:
        load_catalog()
    return dict(_last_health)


def clear_cache() -> None:
    """Force the next load_catalog() call to re-read all sources (Refresh)."""
    if _HAS_STREAMLIT:
        load_catalog.clear()
