"""
Workflow-layer unit tests (the Documentation workspace's read/write seam)
against synthetic fixtures. No Snowflake dependency.
"""

import pandas as pd
import pytest

import config
import data
import workflow


@pytest.fixture
def workflow_fixture(tmp_path):
    """structure.csv + assignments.csv + workspace_query.csv (Source 1) +
    workspace_curated.csv (Source 2), with config pointed at all four.
    structure.csv/DESCRIPTIONS_SOURCE="workflow_table" are only exercised by
    the data.py-side test at the bottom of this file (data._build_catalog_
    and_health() is a separate pipeline from workflow.load_workflow(),
    which now reads data_product/table_count/orphaned from Source 1, not
    data.load_catalog())."""
    structure_rows = [
        ("DB1", "PUBLIC", "TABLE_A", "TRACKED_COL", "VARCHAR(50)"),
        ("DB1", "PUBLIC", "TABLE_B", "TRACKED_COL", "VARCHAR(50)"),
        ("DB1", "PUBLIC", "TABLE_A", "NEW_STRUCTURAL_COL", "NUMBER(10,0)"),
        ("DB2", "PUBLIC", "TABLE_C", "STALE_META_COL", "VARCHAR(20)"),
    ]
    structure_df = pd.DataFrame(
        structure_rows,
        columns=["TABLE_CATALOG", "TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
    )
    structure_path = tmp_path / "structure.csv"
    structure_df.to_csv(structure_path, index=False)

    # Source 1 — same logical shape as structure_rows above, but qualified
    # as one name column (DATA_PRODUCT.SCHEMA.TABLE) the way a real
    # warehouse query returns it, plus its own "live" description.
    # GONE_COL and GLOSSARY_TERM are deliberately absent (orphaned / manual).
    workspace_query_df = pd.DataFrame([
        {"QUALIFIED_OBJECT_NAME": "DB1.PUBLIC.TABLE_A", "COLUMN_NAME": "TRACKED_COL",
         "ORDINAL_POSITION": 1, "DESCRIPTION": "Live: tracked column, table A."},
        {"QUALIFIED_OBJECT_NAME": "DB1.PUBLIC.TABLE_B", "COLUMN_NAME": "TRACKED_COL",
         "ORDINAL_POSITION": 1, "DESCRIPTION": ""},
        {"QUALIFIED_OBJECT_NAME": "DB1.PUBLIC.TABLE_A", "COLUMN_NAME": "NEW_STRUCTURAL_COL",
         "ORDINAL_POSITION": 2, "DESCRIPTION": ""},
        {"QUALIFIED_OBJECT_NAME": "DB2.PUBLIC.TABLE_C", "COLUMN_NAME": "STALE_META_COL",
         "ORDINAL_POSITION": 1, "DESCRIPTION": ""},
    ])
    workspace_query_path = tmp_path / "workspace_query.csv"
    workspace_query_df.to_csv(workspace_query_path, index=False)

    # Source 2 — independent curated feed. TRACKED_COL is both curated AND
    # pre-approved (tests the description_curated vs description_live
    # divergence and the approved->fused-status behavior in one row);
    # NEW_STRUCTURAL_COL is curated but not yet approved (description_curated
    # populated, status stays whatever the workflow table says).
    workspace_curated_df = pd.DataFrame([
        {"column_name": "TRACKED_COL", "description": "Curated: a tracked column.", "approved": "TRUE"},
        {"column_name": "NEW_STRUCTURAL_COL", "description": "Curated draft, not yet approved.", "approved": "FALSE"},
    ])
    workspace_curated_path = tmp_path / "workspace_curated.csv"
    workspace_curated_df.to_csv(workspace_curated_path, index=False)

    assignments_df = pd.DataFrame([
        {"column_name": "TRACKED_COL", "data_product": "DB1", "table_count": 2,
         "description": "A tracked column.", "assigned_to": "Priya", "status": "Submitted",
         "origin": "structure", "orphaned": False, "updated_by": "Priya", "updated_at": "2026-01-01T00:00:00"},
        # Stale table_count/data_product — load_workflow() must refresh these
        # from live structure, not trust what's stored.
        {"column_name": "STALE_META_COL", "data_product": "WRONG_DB", "table_count": 99,
         "description": "", "assigned_to": "", "status": "Unassigned",
         "origin": "structure", "orphaned": False, "updated_by": "", "updated_at": ""},
        # References a column no longer in structure.csv -> orphaned.
        {"column_name": "GONE_COL", "data_product": "DB1", "table_count": 1,
         "description": "Used to exist.", "assigned_to": "Deepak", "status": "Approved",
         "origin": "structure", "orphaned": False, "updated_by": "Deepak", "updated_at": "2025-01-01T00:00:00"},
        # Manual glossary row, also absent from structure -> must NOT be orphaned.
        {"column_name": "GLOSSARY_TERM", "data_product": "DB1", "table_count": 0,
         "description": "A business term.", "assigned_to": "Elena", "status": "Submitted",
         "origin": "manual", "orphaned": False, "updated_by": "Elena", "updated_at": "2026-02-01T00:00:00"},
    ])
    assignments_path = tmp_path / "assignments.csv"
    assignments_df.to_csv(assignments_path, index=False)

    orig = {
        "STRUCT_LOCAL_CSV": dict(config.STRUCT_LOCAL_CSV),
        "STRUCTURE_SOURCE": config.STRUCTURE_SOURCE,
        "DESCRIPTIONS_SOURCE": config.DESCRIPTIONS_SOURCE,
        "DESCRIPTION_MAP": dict(config.DESCRIPTION_MAP),
        "WORKFLOW_SOURCE": config.WORKFLOW_SOURCE,
        "WORKFLOW_LOCAL_CSV": dict(config.WORKFLOW_LOCAL_CSV),
        "WORKFLOW_ASSIGNEES": list(config.WORKFLOW_ASSIGNEES),
        "USAGE_ENABLED": config.USAGE_ENABLED,
        "DATABASE_ALLOWLIST": list(config.DATABASE_ALLOWLIST),
        "WORKSPACE_QUERY_SOURCE": config.WORKSPACE_QUERY_SOURCE,
        "WORKSPACE_QUERY_LOCAL_CSV": dict(config.WORKSPACE_QUERY_LOCAL_CSV),
        "WORKSPACE_QUERY_MAP": dict(config.WORKSPACE_QUERY_MAP),
        "WORKSPACE_QUALIFIED_NAME_DELIMITER": config.WORKSPACE_QUALIFIED_NAME_DELIMITER,
        "WORKSPACE_QUALIFIED_NAME_PARTS": list(config.WORKSPACE_QUALIFIED_NAME_PARTS),
        "WORKSPACE_CURATED_SOURCE": config.WORKSPACE_CURATED_SOURCE,
        "WORKSPACE_CURATED_LOCAL_CSV": dict(config.WORKSPACE_CURATED_LOCAL_CSV),
        "WORKSPACE_CURATED_MAP": dict(config.WORKSPACE_CURATED_MAP),
    }

    config.STRUCT_LOCAL_CSV = {"path": str(structure_path)}
    config.STRUCTURE_SOURCE = "local_csv"
    config.DESCRIPTIONS_SOURCE = "workflow_table"
    config.DESCRIPTION_MAP = {
        "column_name": "column_name", "description": "description", "approved": "status",
    }
    config.WORKFLOW_SOURCE = "local_csv"
    config.WORKFLOW_LOCAL_CSV = {"path": str(assignments_path)}
    config.WORKFLOW_ASSIGNEES = ["Priya", "Deepak", "Marcus", "Elena"]
    config.USAGE_ENABLED = False
    config.DATABASE_ALLOWLIST = []
    config.WORKSPACE_QUERY_SOURCE = "local_csv"
    config.WORKSPACE_QUERY_LOCAL_CSV = {"path": str(workspace_query_path)}
    config.WORKSPACE_QUERY_MAP = {
        "qualified_object_name": "QUALIFIED_OBJECT_NAME", "column_name": "COLUMN_NAME",
        "ordinal_position": "ORDINAL_POSITION", "description": "DESCRIPTION",
    }
    config.WORKSPACE_QUALIFIED_NAME_DELIMITER = "."
    config.WORKSPACE_QUALIFIED_NAME_PARTS = ["data_product", "schema", "table"]
    config.WORKSPACE_CURATED_SOURCE = "local_csv"
    config.WORKSPACE_CURATED_LOCAL_CSV = {"path": str(workspace_curated_path)}
    config.WORKSPACE_CURATED_MAP = {
        "column_name": "column_name", "description": "description", "approved": "approved",
    }

    data.clear_cache()
    yield tmp_path
    data.clear_cache()

    config.STRUCT_LOCAL_CSV = orig["STRUCT_LOCAL_CSV"]
    config.STRUCTURE_SOURCE = orig["STRUCTURE_SOURCE"]
    config.DESCRIPTIONS_SOURCE = orig["DESCRIPTIONS_SOURCE"]
    config.DESCRIPTION_MAP = orig["DESCRIPTION_MAP"]
    config.WORKFLOW_SOURCE = orig["WORKFLOW_SOURCE"]
    config.WORKFLOW_LOCAL_CSV = orig["WORKFLOW_LOCAL_CSV"]
    config.WORKFLOW_ASSIGNEES = orig["WORKFLOW_ASSIGNEES"]
    config.USAGE_ENABLED = orig["USAGE_ENABLED"]
    config.DATABASE_ALLOWLIST = orig["DATABASE_ALLOWLIST"]
    config.WORKSPACE_QUERY_SOURCE = orig["WORKSPACE_QUERY_SOURCE"]
    config.WORKSPACE_QUERY_LOCAL_CSV = orig["WORKSPACE_QUERY_LOCAL_CSV"]
    config.WORKSPACE_QUERY_MAP = orig["WORKSPACE_QUERY_MAP"]
    config.WORKSPACE_QUALIFIED_NAME_DELIMITER = orig["WORKSPACE_QUALIFIED_NAME_DELIMITER"]
    config.WORKSPACE_QUALIFIED_NAME_PARTS = orig["WORKSPACE_QUALIFIED_NAME_PARTS"]
    config.WORKSPACE_CURATED_SOURCE = orig["WORKSPACE_CURATED_SOURCE"]
    config.WORKSPACE_CURATED_LOCAL_CSV = orig["WORKSPACE_CURATED_LOCAL_CSV"]
    config.WORKSPACE_CURATED_MAP = orig["WORKSPACE_CURATED_MAP"]


def _row(df, column_name):
    matches = df[df["column_name"] == column_name]
    assert len(matches) == 1, f"expected exactly one row for {column_name}"
    return matches.iloc[0]


# ─────────────────────────────────────────────────────────────────────────────
# load_workflow — reconcile / auto-seed / orphan detection
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_seeds_untracked_structural_column(workflow_fixture):
    df = workflow.load_workflow()
    seeded = _row(df, "NEW_STRUCTURAL_COL")
    assert seeded["status"] == "Unassigned"
    assert seeded["origin"] == "structure"
    assert seeded["description"] == ""
    assert seeded["assigned_to"] == ""
    # Not persisted just from loading.
    raw = pd.read_csv(config.WORKFLOW_LOCAL_CSV["path"])
    assert "NEW_STRUCTURAL_COL" not in set(raw["column_name"])


def test_orphaned_row_flagged_when_column_missing_from_structure(workflow_fixture):
    df = workflow.load_workflow()
    gone = _row(df, "GONE_COL")
    assert bool(gone["orphaned"]) is True
    assert gone["description"] == "Used to exist."  # preserved, not deleted


def test_manual_row_never_marked_orphaned(workflow_fixture):
    df = workflow.load_workflow()
    manual = _row(df, "GLOSSARY_TERM")
    assert bool(manual["orphaned"]) is False


def test_structure_row_metadata_refreshed_from_live_structure(workflow_fixture):
    df = workflow.load_workflow()
    stale = _row(df, "STALE_META_COL")
    assert stale["data_product"] == "DB2"  # not the stale "WRONG_DB" stored in the CSV
    assert stale["table_count"] == 1       # not the stale 99


def test_tracked_column_not_reseeded(workflow_fixture):
    # STALE_META_COL (not curated-approved, unlike TRACKED_COL in this
    # fixture — see test_curated_approved_fuses_status_to_approved) so its
    # stored status carries straight through with no fusion involved.
    df = workflow.load_workflow()
    matches = df[df["column_name"] == "STALE_META_COL"]
    assert len(matches) == 1
    assert matches.iloc[0]["status"] == "Unassigned"


def test_canonical_field_contract(workflow_fixture):
    """load_workflow() must always return every persisted field (the
    save_rows/_clean_raw contract) plus the derived-only Source 1/2
    overlay columns — but save_rows/_clean_raw themselves only ever see
    CANONICAL_WORKFLOW_FIELDS, so none of the derived columns can leak
    into what's written back to COLUMN_ASSIGNMENTS."""
    df = workflow.load_workflow()
    assert set(workflow.CANONICAL_WORKFLOW_FIELDS) <= set(df.columns)
    for extra in ["tables", "schema", "description_live", "description_curated", "curated_approved"]:
        assert extra in df.columns


# ─────────────────────────────────────────────────────────────────────────────
# Source 1 (query) + Source 2 (curated) join — the locked decisions
# ─────────────────────────────────────────────────────────────────────────────

def test_data_product_and_schema_derived_from_query(workflow_fixture):
    tracked = _row(workflow.load_workflow(), "TRACKED_COL")
    assert tracked["data_product"] == "DB1"
    assert tracked["schema"] == "PUBLIC"


def test_table_count_reflects_distinct_query_tables(workflow_fixture):
    # TRACKED_COL appears in 2 qualified tables in workspace_query.csv,
    # despite assignments.csv's stored table_count also happening to be 2
    # here — table_count now always comes fresh from the query, not the
    # stored value (test_structure_row_metadata_refreshed_from_live_structure
    # already proves a *mismatched* stored value gets overwritten).
    tracked = _row(workflow.load_workflow(), "TRACKED_COL")
    assert tracked["table_count"] == 2
    assert sorted(tracked["tables"]) == ["DB1.PUBLIC.TABLE_A", "DB1.PUBLIC.TABLE_B"]


def test_description_live_and_curated_are_independent(workflow_fixture):
    tracked = _row(workflow.load_workflow(), "TRACKED_COL")
    assert tracked["description_live"] == "Live: tracked column, table A."
    assert tracked["description_curated"] == "Curated: a tracked column."
    assert tracked["description_live"] != tracked["description_curated"]
    # The workflow table's OWN "description" field is untouched by either.
    assert tracked["description"] == "A tracked column."


def test_curated_approved_fuses_status_to_approved(workflow_fixture):
    # TRACKED_COL's stored workflow status is "Submitted", but Source 2
    # marks it approved=TRUE -> the *displayed* status must show Approved.
    tracked = _row(workflow.load_workflow(), "TRACKED_COL")
    assert bool(tracked["curated_approved"]) is True
    assert tracked["status"] == "Approved"


def test_curated_not_approved_leaves_raw_status(workflow_fixture):
    # NEW_STRUCTURAL_COL is curated (has a description_curated) but
    # approved=FALSE -> status stays whatever it already was (auto-seeded
    # Unassigned here), not forced to anything.
    seeded = _row(workflow.load_workflow(), "NEW_STRUCTURAL_COL")
    assert seeded["description_curated"] == "Curated draft, not yet approved."
    assert bool(seeded["curated_approved"]) is False
    assert seeded["status"] == "Unassigned"


def test_column_with_no_curated_row_has_empty_curated_fields(workflow_fixture):
    stale = _row(workflow.load_workflow(), "STALE_META_COL")
    assert stale["description_curated"] == ""
    assert bool(stale["curated_approved"]) is False


# ─────────────────────────────────────────────────────────────────────────────
# Empty-start / null-approved handling
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_seeded_column_never_blank_or_undefined_status(workflow_fixture):
    seeded = _row(workflow.load_workflow(), "NEW_STRUCTURAL_COL")
    assert seeded["status"] == "Unassigned"
    assert seeded["assigned_to"] == ""
    assert seeded["status"] in workflow.STATUSES


def test_null_approved_is_never_treated_as_approved(workflow_fixture):
    # Blank and explicit-None "approved" cells must both resolve to False,
    # never Approved: bool(float('nan')) is True in plain Python, which
    # would be exactly backwards here if a stray NaN ever slipped through.
    curated_df = pd.DataFrame([
        {"column_name": "TRACKED_COL", "description": "desc", "approved": ""},
        {"column_name": "STALE_META_COL", "description": "desc2", "approved": None},
    ])
    curated_df.to_csv(config.WORKSPACE_CURATED_LOCAL_CSV["path"], index=False)

    df = workflow.load_workflow()
    tracked = _row(df, "TRACKED_COL")
    stale = _row(df, "STALE_META_COL")
    assert bool(tracked["curated_approved"]) is False
    assert bool(stale["curated_approved"]) is False
    assert tracked["status"] == "Submitted"   # raw stored status, not fused to Approved
    assert stale["status"] == "Unassigned"


# ─────────────────────────────────────────────────────────────────────────────
# Query-refresh merge guard — assigned_to/status/curated description must
# survive a Source 1 refresh; only structural fields may change.
# ─────────────────────────────────────────────────────────────────────────────

def test_query_structural_vs_protected_fields_are_exactly_as_documented():
    assert set(workflow._QUERY_STRUCTURAL_FIELDS) == {"data_product", "table_count", "tables", "schema"}
    assert set(workflow._QUERY_PROTECTED_FIELDS) == {"assigned_to", "status", "description"}


def test_query_refresh_preserves_assignment_status_and_curated_description(workflow_fixture):
    workflow.save_rows(
        [{"column_name": "STALE_META_COL", "assigned_to": "Marcus", "status": "Assigned"}], actor="coordinator",
    )
    workflow.save_curated_description("STALE_META_COL", "A freshly curated description.")

    # Simulate a query refresh: Source 1 comes back with a different (but
    # still matching) live description for the same column.
    q = pd.read_csv(config.WORKSPACE_QUERY_LOCAL_CSV["path"])
    q.loc[q["COLUMN_NAME"] == "STALE_META_COL", "DESCRIPTION"] = "Refreshed live description."
    q.to_csv(config.WORKSPACE_QUERY_LOCAL_CSV["path"], index=False)

    after = _row(workflow.load_workflow(), "STALE_META_COL")
    assert after["assigned_to"] == "Marcus"
    assert after["status"] == "Assigned"
    assert after["description_curated"] == "A freshly curated description."
    assert after["description_live"] == "Refreshed live description."
    # Structural fields DID refresh from the new query data.
    assert after["data_product"] == "DB2"
    assert after["table_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# unmatched_curated_columns — surfaced instead of silently dropped
# ─────────────────────────────────────────────────────────────────────────────

def test_unmatched_curated_columns_detects_typo(workflow_fixture):
    curated_df = pd.DataFrame([
        {"column_name": "TRACKED_COL", "description": "desc", "approved": "TRUE"},
        {"column_name": "TOTALLY_UNKNOWN_COL", "description": "oops", "approved": "FALSE"},
    ])
    curated_df.to_csv(config.WORKSPACE_CURATED_LOCAL_CSV["path"], index=False)

    assert workflow.unmatched_curated_columns() == ["TOTALLY_UNKNOWN_COL"]
    # Confirmed genuinely dropped, not injected as a phantom row.
    assert "TOTALLY_UNKNOWN_COL" not in set(workflow.load_workflow()["column_name"])


def test_unmatched_curated_columns_empty_when_all_match(workflow_fixture):
    assert workflow.unmatched_curated_columns() == []


def test_manual_row_has_no_live_description_or_tables(workflow_fixture):
    manual = _row(workflow.load_workflow(), "GLOSSARY_TERM")
    assert manual["description_live"] == ""
    assert manual["tables"] == []


def test_split_qualified_name_uses_configured_delimiter_and_parts(workflow_fixture):
    assert workflow._split_qualified_name("DB1.PUBLIC.TABLE_A") == {
        "data_product": "DB1", "schema": "PUBLIC", "table": "TABLE_A",
    }
    config.WORKSPACE_QUALIFIED_NAME_DELIMITER = "/"
    config.WORKSPACE_QUALIFIED_NAME_PARTS = ["schema", "data_product", "table"]
    assert workflow._split_qualified_name("PUBLIC/DB1/TABLE_A") == {
        "schema": "PUBLIC", "data_product": "DB1", "table": "TABLE_A",
    }


# ─────────────────────────────────────────────────────────────────────────────
# save_curated_description — Source 2's own write path
# ─────────────────────────────────────────────────────────────────────────────

def test_save_curated_description_updates_existing_row(workflow_fixture):
    workflow.save_curated_description("TRACKED_COL", "Updated curated text.")
    curated = workflow._load_curated_source()
    row = curated[curated["column_name"] == "TRACKED_COL"].iloc[0]
    assert row["description"] == "Updated curated text."
    assert bool(row["approved"]) is True  # untouched by the description-only save


def test_save_curated_description_inserts_new_row(workflow_fixture):
    workflow.save_curated_description("STALE_META_COL", "First curated draft.")
    curated = workflow._load_curated_source()
    row = curated[curated["column_name"] == "STALE_META_COL"].iloc[0]
    assert row["description"] == "First curated draft."
    assert bool(row["approved"]) is False


def test_save_curated_description_does_not_touch_workflow_table(workflow_fixture):
    workflow.save_curated_description("TRACKED_COL", "Some new curated text.")
    raw = pd.read_csv(config.WORKFLOW_LOCAL_CSV["path"])
    row = raw[raw["column_name"] == "TRACKED_COL"].iloc[0]
    assert row["description"] == "A tracked column."  # workflow's own field, unchanged
    assert row["status"] == "Submitted"  # unchanged


# ─────────────────────────────────────────────────────────────────────────────
# save_rows — row-level upsert + optimistic concurrency
# ─────────────────────────────────────────────────────────────────────────────

def test_save_rows_upserts_existing_row(workflow_fixture):
    workflow.save_rows(
        [{"column_name": "TRACKED_COL", "status": "Approved"}], actor="coordinator",
    )
    df = workflow.load_workflow()
    row = _row(df, "TRACKED_COL")
    assert row["status"] == "Approved"
    assert row["updated_by"] == "coordinator"
    assert row["updated_at"] != "2026-01-01T00:00:00"


def test_save_rows_leaves_other_rows_untouched(workflow_fixture):
    workflow.save_rows(
        [{"column_name": "TRACKED_COL", "status": "Approved"}], actor="coordinator",
    )
    df = workflow.load_workflow()
    untouched = _row(df, "GLOSSARY_TERM")
    assert untouched["updated_by"] == "Elena"
    assert untouched["updated_at"] == "2026-02-01T00:00:00"


def test_save_rows_persists_a_seeded_row_on_first_write(workflow_fixture):
    workflow.save_rows(
        [{"column_name": "NEW_STRUCTURAL_COL", "assigned_to": "Marcus", "status": "Assigned"}],
        actor="coordinator",
    )
    raw = pd.read_csv(config.WORKFLOW_LOCAL_CSV["path"])
    assert "NEW_STRUCTURAL_COL" in set(raw["column_name"])
    row = raw[raw["column_name"] == "NEW_STRUCTURAL_COL"].iloc[0]
    assert row["status"] == "Assigned"
    assert row["assigned_to"] == "Marcus"


def test_save_rows_conflict_raises_on_stale_expected_updated_at(workflow_fixture):
    with pytest.raises(workflow.WorkflowConflictError):
        workflow.save_rows([{
            "column_name": "TRACKED_COL", "status": "Approved",
            "_expected_updated_at": "some-other-timestamp",
        }], actor="deepak")


def test_save_rows_succeeds_when_expected_updated_at_matches(workflow_fixture):
    workflow.save_rows([{
        "column_name": "TRACKED_COL", "status": "Approved",
        "_expected_updated_at": "2026-01-01T00:00:00",
    }], actor="deepak")
    df = workflow.load_workflow()
    assert _row(df, "TRACKED_COL")["status"] == "Approved"


def test_save_rows_clears_catalog_cache_so_approval_is_immediately_visible(workflow_fixture):
    before = data.load_catalog()
    assert bool(_row(before, "TRACKED_COL")["approved"]) is False

    workflow.save_rows([{"column_name": "TRACKED_COL", "status": "Approved"}], actor="coordinator")

    after = data.load_catalog()
    after_row = _row(after, "TRACKED_COL")
    assert bool(after_row["approved"]) is True
    assert after_row["description"] == "A tracked column."


# ─────────────────────────────────────────────────────────────────────────────
# add_manual_row
# ─────────────────────────────────────────────────────────────────────────────

def test_add_manual_row_creates_tracked_row(workflow_fixture):
    workflow.add_manual_row("NET_MARGIN", "DB1", "", actor="priya")
    df = workflow.load_workflow()
    row = _row(df, "NET_MARGIN")
    assert row["origin"] == "manual"
    assert row["status"] == "Unassigned"
    assert row["table_count"] == 0


def test_add_manual_row_sets_table_count_when_table_given(workflow_fixture):
    workflow.add_manual_row("SOME_TERM", "DB1", "DB1.PUBLIC.TABLE_A", actor="priya")
    df = workflow.load_workflow()
    assert _row(df, "SOME_TERM")["table_count"] == 1


def test_add_manual_row_rejects_duplicate(workflow_fixture):
    with pytest.raises(ValueError, match="already tracked"):
        workflow.add_manual_row("TRACKED_COL", "DB1", "", actor="priya")


def test_add_manual_row_requires_column_name(workflow_fixture):
    with pytest.raises(ValueError, match="column_name is required"):
        workflow.add_manual_row("   ", "DB1", "", actor="priya")


def test_add_manual_row_requires_data_product(workflow_fixture):
    with pytest.raises(ValueError, match="data_product is required"):
        workflow.add_manual_row("SOME_COL", "", "", actor="priya")


# ─────────────────────────────────────────────────────────────────────────────
# The workflow_table descriptions source (data.py side) — Approved-only
# ─────────────────────────────────────────────────────────────────────────────

def test_workflow_table_descriptions_source_filters_to_approved(workflow_fixture):
    catalog_df, health = data._build_catalog_and_health()
    tracked = _row(catalog_df, "TRACKED_COL")
    assert tracked["description"] == ""   # Submitted, not Approved -> invisible to the catalog
    assert bool(tracked["approved"]) is False

    workflow.save_rows([{"column_name": "TRACKED_COL", "status": "Approved"}], actor="coordinator")
    catalog_df2, _ = data._build_catalog_and_health()
    tracked2 = _row(catalog_df2, "TRACKED_COL")
    assert tracked2["description"] == "A tracked column."
    assert bool(tracked2["approved"]) is True
