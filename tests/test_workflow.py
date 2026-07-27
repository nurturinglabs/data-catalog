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
    """Small structure.csv + assignments.csv, with config pointed at both
    and DESCRIPTIONS_SOURCE set to "workflow_table" (the default), so
    data.load_catalog() and workflow.load_workflow() operate on the same
    underlying store."""
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
    df = workflow.load_workflow()
    matches = df[df["column_name"] == "TRACKED_COL"]
    assert len(matches) == 1
    assert matches.iloc[0]["status"] == "Submitted"


def test_canonical_field_contract(workflow_fixture):
    df = workflow.load_workflow()
    assert list(df.columns) == workflow.CANONICAL_WORKFLOW_FIELDS


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
