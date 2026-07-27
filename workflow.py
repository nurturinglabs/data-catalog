"""
workflow.py — the read/write seam for the Documentation workspace (the
authoring side of descriptions). Owns the COLUMN_ASSIGNMENTS table: loading
it, reconciling it against live structure (auto-seed new columns, flag
orphaned ones), row-level write-back, and current-user resolution.

data.py's own read of descriptions (DESCRIPTIONS_SOURCE == "workflow_table")
reads the *same* underlying store this module writes to, filtered to
Approved rows — see data.py's `_read_descriptions_workflow_table`. This
module must never be imported by data.py (write concerns stay out of the
read seam); it imports data.py instead, to build off the live catalog for
seeding/reconciliation.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd

import config
import data

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


CANONICAL_WORKFLOW_FIELDS = [
    "column_name",
    "data_product",
    "table_count",
    "description",
    "assigned_to",
    "status",
    "origin",
    "orphaned",
    "updated_by",
    "updated_at",
]

STATUSES = ["Unassigned", "Assigned", "In progress", "Submitted", "Approved"]
OPEN_STATUSES = ["Unassigned", "Assigned", "In progress"]  # an assignee's "not done yet"


class WorkflowConflictError(Exception):
    """A row's stored updated_at differs from what the caller last saw —
    someone else changed it since this session loaded it."""


# ─────────────────────────────────────────────────────────────────────────────
# Raw read/write — dispatches on WORKFLOW_SOURCE, mirrors data.py's pattern
# ─────────────────────────────────────────────────────────────────────────────

def _read_workflow_local_csv() -> pd.DataFrame:
    cfg = config.WORKFLOW_LOCAL_CSV
    try:
        return pd.read_csv(cfg["path"])
    except FileNotFoundError:
        return pd.DataFrame(columns=CANONICAL_WORKFLOW_FIELDS)
    except Exception as exc:
        raise data.DataSourceError(f"Could not read local CSV '{cfg['path']}': {exc}") from exc


def _read_workflow_snowflake_table() -> pd.DataFrame:
    cfg = config.WORKFLOW_TABLE
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.table(cfg["table"]).to_pandas()
    except Exception as exc:
        raise data.DataSourceError(f"Could not read table '{cfg['table']}': {exc}") from exc


def _read_raw() -> pd.DataFrame:
    if config.WORKFLOW_SOURCE == "local_csv":
        return _read_workflow_local_csv()
    if config.WORKFLOW_SOURCE == "snowflake_table":
        return _read_workflow_snowflake_table()
    raise data.DataSourceError(f"Unknown WORKFLOW_SOURCE: {config.WORKFLOW_SOURCE!r}")


def _write_workflow_local_csv(df: pd.DataFrame) -> None:
    cfg = config.WORKFLOW_LOCAL_CSV
    df.to_csv(cfg["path"], index=False)


def _write_workflow_snowflake_table(df: pd.DataFrame) -> None:
    """Template MERGE-based writer — validate against a real table/session
    before relying on it, exactly like data.py's USAGE_QUERY template. A
    real implementation would MERGE just the touched rows (a temp/staged
    frame keyed on column_name) rather than overwrite the table; sketched
    here as the config-only extension point, not exercised locally."""
    cfg = config.WORKFLOW_TABLE
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
    session.write_pandas(df, cfg["table"], overwrite=True, auto_create_table=False)


def _write_raw(df: pd.DataFrame) -> None:
    if config.WORKFLOW_SOURCE == "local_csv":
        _write_workflow_local_csv(df)
    elif config.WORKFLOW_SOURCE == "snowflake_table":
        _write_workflow_snowflake_table(df)
    else:
        raise data.DataSourceError(f"Unknown WORKFLOW_SOURCE: {config.WORKFLOW_SOURCE!r}")


def _clean_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Coerce a freshly-read raw frame onto CANONICAL_WORKFLOW_FIELDS with
    the right dtypes, tolerating a totally empty/missing source (first run,
    no assignments.csv yet)."""
    out = pd.DataFrame(index=raw.index)
    for field in CANONICAL_WORKFLOW_FIELDS:
        if field in raw.columns:
            out[field] = raw[field]
        elif field == "table_count":
            out[field] = 0
        elif field == "orphaned":
            out[field] = False
        else:
            out[field] = ""
    out["column_name"] = out["column_name"].astype(str).str.strip()
    out = out[out["column_name"] != ""]
    out["table_count"] = pd.to_numeric(out["table_count"], errors="coerce").fillna(0).astype(int)
    out["orphaned"] = out["orphaned"].map(data._parse_bool) if len(out) else out["orphaned"]
    for field in ["data_product", "description", "assigned_to", "status", "origin", "updated_by", "updated_at"]:
        out[field] = out[field].map(data._clean_cell)
    return out.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Load + reconcile — auto-seed new structural columns, flag orphaned ones.
# Uncached and always computed fresh: this table is written to constantly
# from the workspace page, and it's small (hundreds of rows, not the
# structure/usage scale), so a cache-invalidation dance isn't worth the risk.
# ─────────────────────────────────────────────────────────────────────────────

def load_workflow() -> pd.DataFrame:
    catalog_df = data.load_catalog()
    catalog_by_col = {row["column_name"]: row for _, row in catalog_df.iterrows()}

    raw = _clean_raw(_read_raw())
    records = []
    seen = set()

    for _, r in raw.iterrows():
        col = r["column_name"]
        seen.add(col)
        rec = r.to_dict()
        if r["origin"] == "manual":
            rec["orphaned"] = False
        else:
            cat_row = catalog_by_col.get(col)
            if cat_row is None:
                rec["orphaned"] = True
            else:
                rec["orphaned"] = False
                rec["data_product"] = ", ".join(cat_row["databases"])
                rec["table_count"] = len(cat_row["tables"])
        records.append(rec)

    # Auto-seed: every catalog column not already tracked here appears as a
    # fresh Unassigned/structure row. Not persisted until something acts on
    # it (assign/edit/etc.) — see save_rows.
    for _, cat_row in catalog_df.iterrows():
        col = cat_row["column_name"]
        if col in seen:
            continue
        records.append({
            "column_name": col,
            "data_product": ", ".join(cat_row["databases"]),
            "table_count": len(cat_row["tables"]),
            "description": "",
            "assigned_to": "",
            "status": "Unassigned",
            "origin": "structure",
            "orphaned": False,
            "updated_by": "",
            "updated_at": "",
        })

    if not records:
        return pd.DataFrame(columns=CANONICAL_WORKFLOW_FIELDS)
    return pd.DataFrame(records, columns=CANONICAL_WORKFLOW_FIELDS)


# ─────────────────────────────────────────────────────────────────────────────
# Write — row-level upsert with optimistic-concurrency conflict detection
# ─────────────────────────────────────────────────────────────────────────────

def save_rows(edits: list[dict], actor: str, check_conflicts: bool = True) -> None:
    """Upsert `edits` (each a dict with at least "column_name" plus the
    fields being changed) into the persisted store, touching only those
    rows — every other row is round-tripped untouched. Sets updated_by and
    updated_at automatically. If an edit carries "_expected_updated_at" and
    check_conflicts is True, raises WorkflowConflictError when the row's
    currently-stored updated_at doesn't match (someone else changed it since
    this session loaded it)."""
    if not edits:
        return

    current = _clean_raw(_read_raw())
    now = _dt.datetime.now().isoformat(timespec="seconds")

    for edit in edits:
        edit = dict(edit)
        col = edit["column_name"]
        expected_updated_at = edit.pop("_expected_updated_at", None)
        by_col = {name: idx for idx, name in current["column_name"].items()}

        if col in by_col:
            idx = by_col[col]
            if check_conflicts and expected_updated_at is not None:
                stored_at = str(current.at[idx, "updated_at"])
                if stored_at != str(expected_updated_at):
                    raise WorkflowConflictError(
                        f"'{col}' was updated by someone else since you loaded it "
                        f"(now updated_by={current.at[idx, 'updated_by']!r} "
                        f"at {stored_at!r})."
                    )
            edit["updated_by"] = actor
            edit["updated_at"] = now
            for k, v in edit.items():
                if k in current.columns:
                    current.at[idx, k] = v
        else:
            new_row = {f: "" for f in CANONICAL_WORKFLOW_FIELDS}
            new_row.update({
                "table_count": 0, "orphaned": False, "origin": "structure",
                "status": "Unassigned",
            })
            new_row.update(edit)
            new_row["updated_by"] = actor
            new_row["updated_at"] = now
            current = pd.concat(
                [current, pd.DataFrame([new_row], columns=CANONICAL_WORKFLOW_FIELDS)],
                ignore_index=True,
            )

    _write_raw(current[CANONICAL_WORKFLOW_FIELDS])
    # A save may have just approved (or un-approved) a description — the
    # catalog's cached read of the same underlying table must not go stale.
    data.clear_cache()


def add_manual_row(column_name: str, data_product: str, table: str, actor: str) -> None:
    """Coordinator "Add row" control — a business-glossary term or
    not-yet-built column with no physical structure entry."""
    column_name = column_name.strip().upper()
    if not column_name:
        raise ValueError("column_name is required.")
    if not data_product:
        raise ValueError("data_product is required.")
    existing = load_workflow()
    if column_name in set(existing["column_name"]):
        raise ValueError(f"'{column_name}' is already tracked in the workspace.")

    save_rows([{
        "column_name": column_name,
        "data_product": data_product,
        "table_count": 1 if table else 0,
        "description": "",
        "assigned_to": "",
        "status": "Unassigned",
        "origin": "manual",
        "orphaned": False,
    }], actor=actor)


# ─────────────────────────────────────────────────────────────────────────────
# Identity — SiS resolves CURRENT_USER(); locally, a session-backed picker.
# ─────────────────────────────────────────────────────────────────────────────

def is_sis() -> bool:
    try:
        from snowflake.snowpark.context import get_active_session
        get_active_session()
        return True
    except Exception:
        return False


def _default_local_user() -> str:
    return config.WORKFLOW_ASSIGNEES[0] if config.WORKFLOW_ASSIGNEES else "me"


def current_user() -> str:
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.sql("SELECT CURRENT_USER() AS U").collect()[0]["U"]
    except Exception:
        pass
    if _HAS_STREAMLIT:
        return st.session_state.get("workflow_current_user", _default_local_user())
    return _default_local_user()


def set_local_user(name: str) -> None:
    """Local dev only — the page's user picker calls this on change."""
    if _HAS_STREAMLIT:
        st.session_state["workflow_current_user"] = name
