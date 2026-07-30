"""
workflow.py — the read/write seam for the Documentation workspace (the
authoring side of descriptions). Owns three things:

1. The COLUMN_ASSIGNMENTS table (Layer 4 in config.py) — assigned_to and
   status bookkeeping, row-level write-back, current-user resolution.
2. Source 1, "the query" (Layer 5) — a live structure+description feed
   shaped as one qualified_object_name column (not separate
   database/schema/table columns), the way a real warehouse query actually
   returns it. Reconciliation (auto-seed new columns, flag orphaned ones)
   and data_product/table_count now come from HERE, not from
   data.load_catalog() — this is workspace-local structure, decoupled from
   the Catalog page's own STRUCTURE_SOURCE pipeline.
3. Source 2, "the curated CSV" (Layer 5) — an independently curated
   descriptions/approval feed. Its description is the workspace grid's
   editable "Description (curated)" field (saved via
   save_curated_description, a separate write path from save_rows); its
   approved flag feeds into the *displayed* Status (Approved overrides
   whatever the workflow's own stored status is) without changing what's
   actually persisted in COLUMN_ASSIGNMENTS.

data.py's own read of descriptions (DESCRIPTIONS_SOURCE == "workflow_table")
still reads the COLUMN_ASSIGNMENTS store directly, filtered to Approved
rows — see data.py's `_read_descriptions_workflow_table`. That path, and
the Catalog page it feeds, are untouched by Sources 1/2 above. This module
must never be imported by data.py (write concerns stay out of the read
seam); it imports data.py instead, for its DataSourceError/_clean_cell/
_parse_bool/_ci_header_lookup helpers and (Layer 4 only) cache invalidation.
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
# Source 1 — the live structure+description query. Workspace-local: this
# is NOT data.py's STRUCTURE_SOURCE/STRUCTURE_MAP (which stays untouched,
# still feeding the Catalog page) — a real warehouse query typically
# returns one already-qualified name column rather than separate
# database/schema/table columns, so this gets its own reader + split logic.
# ─────────────────────────────────────────────────────────────────────────────

def _read_workspace_query_local_csv() -> pd.DataFrame:
    cfg = config.WORKSPACE_QUERY_LOCAL_CSV
    try:
        return pd.read_csv(cfg["path"])
    except Exception as exc:
        raise data.DataSourceError(f"Could not read local CSV '{cfg['path']}': {exc}") from exc


def _read_workspace_query_snowflake() -> pd.DataFrame:
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.sql(config.WORKSPACE_QUERY_SQL).to_pandas()
    except Exception as exc:
        raise data.DataSourceError(f"Could not query workspace structure source: {exc}") from exc


def _read_query_raw() -> pd.DataFrame:
    if config.WORKSPACE_QUERY_SOURCE == "local_csv":
        return _read_workspace_query_local_csv()
    if config.WORKSPACE_QUERY_SOURCE == "snowflake_query":
        return _read_workspace_query_snowflake()
    raise data.DataSourceError(f"Unknown WORKSPACE_QUERY_SOURCE: {config.WORKSPACE_QUERY_SOURCE!r}")


def _split_qualified_name(name: str) -> dict:
    """Split a qualified_object_name into its configured parts
    (WORKSPACE_QUALIFIED_NAME_DELIMITER / _PARTS) — e.g.
    "FINANCE_DB.PUBLIC.INVOICES" -> {"data_product": "FINANCE_DB",
    "schema": "PUBLIC", "table": "INVOICES"} by default. A name with fewer
    segments than configured just leaves the missing parts blank, rather
    than raising, so one malformed row doesn't take down the whole load."""
    parts = [p.strip() for p in name.split(config.WORKSPACE_QUALIFIED_NAME_DELIMITER)]
    labels = config.WORKSPACE_QUALIFIED_NAME_PARTS
    result = {label: "" for label in labels}
    for label, part in zip(labels, parts):
        result[label] = part
    return result


def _load_query_source() -> pd.DataFrame:
    """Source 1, collapsed to one row per column_name — the same JOIN_GRAIN
    concept as data.py's catalog, computed independently here:
    data_product/schema (comma-joined distinct values), table_count
    (distinct qualified tables — this is what "N tables" now means in the
    workspace grid), tables (sorted qualified table list, used for the
    Assignee view's "appears in" context), and description (the query's
    own "live" description — first non-empty value found, sorted for
    determinism if it varies by table)."""
    raw = _read_query_raw()
    ci_lookup = data._ci_header_lookup(raw.columns)
    qmap = config.WORKSPACE_QUERY_MAP

    def _header(field):
        name = qmap.get(field)
        return ci_lookup.get(str(name).strip().lower()) if name else None

    qual_header = _header("qualified_object_name")
    name_header = _header("column_name")
    desc_header = _header("description")
    if qual_header is None or name_header is None:
        raise data.DataSourceError(
            "[workspace query] missing required header(s) for "
            f"qualified_object_name/column_name. Columns present: {list(raw.columns)}"
        )

    out = pd.DataFrame()
    out["qualified_object_name"] = raw[qual_header].map(data._clean_cell)
    out["column_name"] = raw[name_header].map(data._clean_cell).str.upper()
    out["description"] = raw[desc_header].map(data._clean_cell) if desc_header else ""
    out = out[(out["column_name"] != "") & (out["qualified_object_name"] != "")]

    parts = config.WORKSPACE_QUALIFIED_NAME_PARTS
    split = out["qualified_object_name"].map(_split_qualified_name).apply(pd.Series)
    for label in parts:
        if label not in split.columns:
            split[label] = ""
    out = pd.concat([out.reset_index(drop=True), split.reset_index(drop=True)], axis=1)

    product_field = "data_product" if "data_product" in parts else parts[0]
    schema_field = "schema" if "schema" in parts else (parts[1] if len(parts) > 1 else parts[0])

    if out.empty:
        return pd.DataFrame(columns=["column_name", "data_product", "schema", "table_count", "tables", "description"])

    rows = []
    for col, group in out.groupby("column_name", sort=True):
        qualified_tables = sorted(group["qualified_object_name"].unique().tolist())
        products = sorted({p for p in group[product_field] if p})
        schemas = sorted({s for s in group[schema_field] if s})
        descs = sorted(d for d in group["description"] if d)
        rows.append({
            "column_name": col,
            "data_product": ", ".join(products),
            "schema": ", ".join(schemas),
            "table_count": len(qualified_tables),
            "tables": qualified_tables,
            "description": descs[0] if descs else "",
        })
    return pd.DataFrame(
        rows, columns=["column_name", "data_product", "schema", "table_count", "tables", "description"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Source 2 — the curated descriptions/approval feed. Independent of the
# COLUMN_ASSIGNMENTS table above (assigned_to/status stay there,
# unchanged) and of data.py's DESCRIPTIONS_SOURCE (which stays
# "workflow_table", still feeding the Catalog page — this source does not
# touch that path). Its description is the workspace grid's editable
# "Description (curated)" field; its approved flag feeds the *displayed*
# Status only (see load_workflow) without altering what's persisted in
# COLUMN_ASSIGNMENTS.
# ─────────────────────────────────────────────────────────────────────────────

def _read_workspace_curated_local_csv() -> pd.DataFrame:
    cfg = config.WORKSPACE_CURATED_LOCAL_CSV
    try:
        return pd.read_csv(cfg["path"])
    except Exception as exc:
        raise data.DataSourceError(f"Could not read local CSV '{cfg['path']}': {exc}") from exc


def _read_workspace_curated_snowflake_table() -> pd.DataFrame:
    cfg = config.WORKSPACE_CURATED_TABLE
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        return session.table(cfg["table"]).to_pandas()
    except Exception as exc:
        raise data.DataSourceError(f"Could not read table '{cfg['table']}': {exc}") from exc


def _read_curated_raw() -> pd.DataFrame:
    if config.WORKSPACE_CURATED_SOURCE == "local_csv":
        return _read_workspace_curated_local_csv()
    if config.WORKSPACE_CURATED_SOURCE == "snowflake_table":
        return _read_workspace_curated_snowflake_table()
    raise data.DataSourceError(f"Unknown WORKSPACE_CURATED_SOURCE: {config.WORKSPACE_CURATED_SOURCE!r}")


def _write_workspace_curated_local_csv(df: pd.DataFrame) -> None:
    cfg = config.WORKSPACE_CURATED_LOCAL_CSV
    df.to_csv(cfg["path"], index=False)


def _write_workspace_curated_snowflake_table(df: pd.DataFrame) -> None:
    """Template MERGE-based writer — same caveat as
    _write_workflow_snowflake_table above: validate against a real
    table/session before relying on it."""
    cfg = config.WORKSPACE_CURATED_TABLE
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
    session.write_pandas(df, cfg["table"], overwrite=True, auto_create_table=False)


def _write_curated_raw(df: pd.DataFrame) -> None:
    if config.WORKSPACE_CURATED_SOURCE == "local_csv":
        _write_workspace_curated_local_csv(df)
    elif config.WORKSPACE_CURATED_SOURCE == "snowflake_table":
        _write_workspace_curated_snowflake_table(df)
    else:
        raise data.DataSourceError(f"Unknown WORKSPACE_CURATED_SOURCE: {config.WORKSPACE_CURATED_SOURCE!r}")


def _load_curated_source() -> pd.DataFrame:
    """Source 2, canonicalized: column_name, description, approved."""
    raw = _read_curated_raw()
    ci_lookup = data._ci_header_lookup(raw.columns)
    cmap = config.WORKSPACE_CURATED_MAP

    def _header(field):
        name = cmap.get(field)
        return ci_lookup.get(str(name).strip().lower()) if name else None

    name_header = _header("column_name")
    desc_header = _header("description")
    approved_header = _header("approved")
    if name_header is None:
        raise data.DataSourceError(
            "[workspace curated] missing required header 'column_name'. "
            f"Columns present: {list(raw.columns)}"
        )

    out = pd.DataFrame()
    out["column_name"] = raw[name_header].map(data._clean_cell).str.upper()
    out["description"] = raw[desc_header].map(data._clean_cell) if desc_header else ""
    out["approved"] = raw[approved_header].map(data._parse_bool) if approved_header else False
    out = out[out["column_name"] != ""]
    return out.drop_duplicates(subset="column_name", keep="last").reset_index(drop=True)


def save_curated_description(column_name: str, description: str) -> None:
    """Upsert just this column's curated description into Source 2 — the
    save target for the workspace grid's editable "Description (curated)"
    field. Does not touch approved (an external curated-source input, not
    settable from this UI) or anything in COLUMN_ASSIGNMENTS
    (assigned_to/status stay exactly as they are — use save_rows for
    those)."""
    column_name = column_name.strip().upper()
    current = _load_curated_source()
    mask = current["column_name"] == column_name
    if mask.any():
        current.loc[mask, "description"] = description
    else:
        new_row = pd.DataFrame([{"column_name": column_name, "description": description, "approved": False}])
        current = pd.concat([current, new_row], ignore_index=True)
    _write_curated_raw(current[["column_name", "description", "approved"]])


# ─────────────────────────────────────────────────────────────────────────────
# Load + reconcile — auto-seed new structural columns, flag orphaned ones.
# Uncached and always computed fresh: this table is written to constantly
# from the workspace page, and it's small (hundreds of rows, not the
# structure/usage scale), so a cache-invalidation dance isn't worth the risk.
# ─────────────────────────────────────────────────────────────────────────────

def load_workflow() -> pd.DataFrame:
    """Returns CANONICAL_WORKFLOW_FIELDS (the persisted COLUMN_ASSIGNMENTS
    shape — save_rows/_clean_raw only ever see this subset, so nothing
    below can leak into what gets written back) PLUS derived-only columns
    computed fresh on every call, never persisted:
      - tables: sorted qualified table list (Source 1) — Assignee "appears
        in" context.
      - description_live: Source 1's own description (read-only).
      - description_curated: Source 2's description (the editable field —
        see save_curated_description).
      - curated_approved: Source 2's approved flag.
    "status" is overwritten with the fused display value (Approved when
    curated_approved is True, else the stored workflow status) — this *is*
    "the Status column" per the join spec, not a separate field; the raw
    persisted status is what save_rows/_clean_raw read straight off disk,
    so bulk Assign/Approve continue to operate on real, unfused values."""
    query_df = _load_query_source()
    query_by_col = {row["column_name"]: row for _, row in query_df.iterrows()}
    curated_df = _load_curated_source()
    curated_by_col = curated_df.set_index("column_name")[["description", "approved"]].to_dict("index")

    raw = _clean_raw(_read_raw())
    records = []
    seen = set()

    for _, r in raw.iterrows():
        col = r["column_name"]
        seen.add(col)
        rec = r.to_dict()
        if r["origin"] == "manual":
            rec["orphaned"] = False
            rec["tables"] = []
            rec["schema"] = ""
        else:
            q_row = query_by_col.get(col)
            if q_row is None:
                rec["orphaned"] = True
                rec["tables"] = []
                rec["schema"] = ""
            else:
                rec["orphaned"] = False
                rec["data_product"] = q_row["data_product"]
                rec["table_count"] = int(q_row["table_count"])
                rec["tables"] = q_row["tables"]
                rec["schema"] = q_row["schema"]
        records.append(rec)

    # Auto-seed: every query column not already tracked here appears as a
    # fresh Unassigned/structure row. Not persisted until something acts on
    # it (assign/edit/etc.) — see save_rows.
    for _, q_row in query_df.iterrows():
        col = q_row["column_name"]
        if col in seen:
            continue
        records.append({
            "column_name": col,
            "data_product": q_row["data_product"],
            "table_count": int(q_row["table_count"]),
            "tables": q_row["tables"],
            "schema": q_row["schema"],
            "description": "",
            "assigned_to": "",
            "status": "Unassigned",
            "origin": "structure",
            "orphaned": False,
            "updated_by": "",
            "updated_at": "",
        })

    extra_fields = ["tables", "schema"]
    if not records:
        df = pd.DataFrame(columns=CANONICAL_WORKFLOW_FIELDS + extra_fields)
    else:
        df = pd.DataFrame(records)
        for field in CANONICAL_WORKFLOW_FIELDS:
            if field not in df.columns:
                df[field] = 0 if field == "table_count" else ("" if field != "orphaned" else False)
        df = df[CANONICAL_WORKFLOW_FIELDS + extra_fields]

    df["description_live"] = df["column_name"].map(
        lambda c: query_by_col[c]["description"] if c in query_by_col else ""
    )
    df["description_curated"] = df["column_name"].map(
        lambda c: curated_by_col[c]["description"] if c in curated_by_col else ""
    )
    df["curated_approved"] = df["column_name"].map(
        lambda c: bool(curated_by_col[c]["approved"]) if c in curated_by_col else False
    )
    df["status"] = [
        "Approved" if approved else status
        for approved, status in zip(df["curated_approved"], df["status"])
    ]
    return df


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
