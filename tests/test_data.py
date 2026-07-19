"""
Data-layer unit tests against synthetic fixtures. No Snowflake dependency —
tests point config at small in-memory/temp-file fixtures and call the
uncached pipeline directly.
"""

import importlib
import os

import pandas as pd
import pytest

import config
import data


@pytest.fixture
def fixture_dir(tmp_path):
    """Write small structure.csv / descriptions.csv fixtures and point
    config at them for the duration of one test."""
    structure_rows = [
        # CUSIP-like shared column across 3 tables -> non-trivial reverse index
        ("DB1", "PUBLIC", "TABLE_A", "SHARED_ID", "VARCHAR(9)"),
        ("DB1", "PUBLIC", "TABLE_B", "SHARED_ID", "VARCHAR(9)"),
        ("DB2", "PUBLIC", "TABLE_C", "SHARED_ID", "VARCHAR(9)"),
        # documented, single-table column
        ("DB1", "PUBLIC", "TABLE_A", "NAME", "VARCHAR(100)"),
        # undocumented column (present in structure, absent from descriptions)
        ("DB1", "PUBLIC", "TABLE_A", "MYSTERY_COL", "NUMBER(10,0)"),
        # data_type mode test: 2x NUMBER, 1x VARCHAR for the same column
        ("DB2", "SCHEMA_X", "TABLE_D", "MODE_COL", "NUMBER(38,0)"),
        ("DB2", "SCHEMA_X", "TABLE_E", "MODE_COL", "NUMBER(38,0)"),
        ("DB2", "SCHEMA_Y", "TABLE_F", "MODE_COL", "VARCHAR(50)"),
        # row with nan-ish junk that should clean to empty and get dropped
    ]
    structure_df = pd.DataFrame(
        structure_rows,
        columns=["TABLE_CATALOG", "TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
    )
    structure_path = tmp_path / "structure.csv"
    structure_df.to_csv(structure_path, index=False)

    descriptions_df = pd.DataFrame([
        {"Column Name": "SHARED_ID", "Description": "A shared identifier.",
         "Tags": "PII, Certified", "Steward": "Gov"},
        {"Column Name": "NAME", "Description": "  A display name.  ",
         "Tags": "nan", "Steward": "NULL"},
        {"Column Name": "MODE_COL", "Description": "Mode test column.",
         "Tags": "", "Steward": ""},
        # MYSTERY_COL intentionally absent -> undocumented
    ])
    descriptions_path = tmp_path / "descriptions.csv"
    descriptions_df.to_csv(descriptions_path, index=False)

    orig = {
        "STRUCT_LOCAL_CSV": dict(config.STRUCT_LOCAL_CSV),
        "DESC_CSV_LOCAL": dict(config.DESC_CSV_LOCAL),
        "DESCRIPTIONS_SOURCE": config.DESCRIPTIONS_SOURCE,
        "JOIN_GRAIN": config.JOIN_GRAIN,
        "CATALOG_SPINE": config.CATALOG_SPINE,
        "DATABASE_ALLOWLIST": list(config.DATABASE_ALLOWLIST),
        "DESCRIPTION_MAP": dict(config.DESCRIPTION_MAP),
        "MAX_STRUCTURE_ROWS": config.MAX_STRUCTURE_ROWS,
        "USAGE_ENABLED": config.USAGE_ENABLED,
        "USAGE_SOURCE": config.USAGE_SOURCE,
        "USAGE_LOCAL_CSV": dict(config.USAGE_LOCAL_CSV),
        "USAGE_MAP": dict(config.USAGE_MAP),
    }

    config.STRUCT_LOCAL_CSV = {"path": str(structure_path)}
    config.DESC_CSV_LOCAL = {"path": str(descriptions_path)}
    config.DESCRIPTIONS_SOURCE = "csv_local"
    # No usage.csv by default — points at a path that doesn't exist, so
    # every test gets a deterministic graceful "unavailable" fallback
    # (consumers=[]) unless it explicitly opts in with its own usage fixture.
    config.USAGE_ENABLED = True
    config.USAGE_SOURCE = "local_csv"
    config.USAGE_LOCAL_CSV = {"path": str(tmp_path / "usage.csv")}

    yield tmp_path

    config.STRUCT_LOCAL_CSV = orig["STRUCT_LOCAL_CSV"]
    config.DESC_CSV_LOCAL = orig["DESC_CSV_LOCAL"]
    config.DESCRIPTIONS_SOURCE = orig["DESCRIPTIONS_SOURCE"]
    config.JOIN_GRAIN = orig["JOIN_GRAIN"]
    config.CATALOG_SPINE = orig["CATALOG_SPINE"]
    config.DATABASE_ALLOWLIST = orig["DATABASE_ALLOWLIST"]
    config.DESCRIPTION_MAP = orig["DESCRIPTION_MAP"]
    config.MAX_STRUCTURE_ROWS = orig["MAX_STRUCTURE_ROWS"]
    config.USAGE_ENABLED = orig["USAGE_ENABLED"]
    config.USAGE_SOURCE = orig["USAGE_SOURCE"]
    config.USAGE_LOCAL_CSV = orig["USAGE_LOCAL_CSV"]
    config.USAGE_MAP = orig["USAGE_MAP"]


def _row(df, column_name):
    matches = df[df["column_name"] == column_name]
    assert len(matches) == 1, f"expected exactly one row for {column_name}"
    return matches.iloc[0]


def test_cleaning_nan_and_whitespace_to_empty(fixture_dir):
    df, _ = data._build_catalog_and_health()
    name_row = _row(df, "NAME")
    assert name_row["description"] == "A display name."
    assert name_row["tags"] == []
    assert name_row["steward"] == ""


def test_cleaning_delimited_to_list(fixture_dir):
    df, _ = data._build_catalog_and_health()
    shared = _row(df, "SHARED_ID")
    assert shared["tags"] == ["PII", "Certified"]


def test_reverse_index_shared_column(fixture_dir):
    df, _ = data._build_catalog_and_health()
    shared = _row(df, "SHARED_ID")
    assert shared["tables"] == ["DB1.PUBLIC.TABLE_A", "DB1.PUBLIC.TABLE_B", "DB2.PUBLIC.TABLE_C"]
    assert shared["databases"] == ["DB1", "DB2"]
    assert shared["schemas"] == ["DB1.PUBLIC", "DB2.PUBLIC"]


def test_data_type_is_representative_mode(fixture_dir):
    df, _ = data._build_catalog_and_health()
    mode_row = _row(df, "MODE_COL")
    assert mode_row["data_type"] == "NUMBER(38,0)"


def test_join_grain_column_name_vs_schema_column(fixture_dir):
    config.JOIN_GRAIN = "column_name"
    df_col, _ = data._build_catalog_and_health()
    assert len(df_col[df_col["column_name"] == "SHARED_ID"]) == 1

    config.JOIN_GRAIN = "schema.column"
    df_schema, _ = data._build_catalog_and_health()
    # SHARED_ID spans DB1.PUBLIC and DB2.PUBLIC -> 2 entries at this grain
    assert len(df_schema[df_schema["column_name"] == "SHARED_ID"]) == 2


def test_spine_structure_includes_undocumented(fixture_dir):
    config.CATALOG_SPINE = "structure"
    df, _ = data._build_catalog_and_health()
    assert "MYSTERY_COL" in set(df["column_name"])
    mystery = _row(df, "MYSTERY_COL")
    assert bool(mystery["documented"]) is False
    assert mystery["description"] == ""


def test_spine_descriptions_excludes_undocumented(fixture_dir):
    config.CATALOG_SPINE = "descriptions"
    df, _ = data._build_catalog_and_health()
    assert "MYSTERY_COL" not in set(df["column_name"])
    assert bool(df["documented"].all())


def test_coverage_matches_fixture(fixture_dir):
    df, health = data._build_catalog_and_health()
    documented = int(df["documented"].sum())
    total = len(df)
    # SHARED_ID, NAME, MODE_COL documented; MYSTERY_COL undocumented -> 3/4
    assert documented == 3
    assert total == 4
    assert health["documented_count"] == documented
    assert health["entry_count"] == total
    assert health["coverage_pct"] == pytest.approx(75.0)


def test_contract_columns_match_canonical_fields(fixture_dir):
    df, _ = data._build_catalog_and_health()
    assert list(df.columns) == data.CANONICAL_FIELDS
    assert (df["tables"].map(len) > 0).all()


def test_validation_missing_required_header_raises(fixture_dir):
    config.DESCRIPTION_MAP = dict(config.DESCRIPTION_MAP)
    config.DESCRIPTION_MAP["column_name"] = "Nonexistent Header"
    with pytest.raises(ValueError, match="missing required header"):
        data._build_catalog_and_health()


def test_validation_missing_optional_header_does_not_raise(fixture_dir):
    config.DESCRIPTION_MAP = dict(config.DESCRIPTION_MAP)
    del config.DESCRIPTION_MAP["steward"]
    df, health = data._build_catalog_and_health()
    assert "steward" in health["descriptions_headers_missing_optional"]
    assert (df["steward"] == "").all()


def test_database_allowlist_restricts_structure(fixture_dir):
    config.DATABASE_ALLOWLIST = ["DB1"]
    df, _ = data._build_catalog_and_health()
    all_dbs = {db for row in df["databases"] for db in row}
    assert all_dbs == {"DB1"}


def test_approved_defaults_false_without_column(fixture_dir):
    # The fixture's descriptions.csv has no "Approved" header at all.
    df, _ = data._build_catalog_and_health()
    assert not df["approved"].any()


def test_approved_parses_truthy_tokens(fixture_dir):
    descriptions_df = pd.DataFrame([
        {"Column Name": "SHARED_ID", "Description": "desc", "Tags": "", "Steward": "", "Approved": "TRUE"},
        {"Column Name": "NAME", "Description": "desc", "Tags": "", "Steward": "", "Approved": "no"},
        {"Column Name": "MODE_COL", "Description": "desc", "Tags": "", "Steward": "", "Approved": ""},
    ])
    descriptions_df.to_csv(config.DESC_CSV_LOCAL["path"], index=False)

    df, _ = data._build_catalog_and_health()
    assert bool(_row(df, "SHARED_ID")["approved"]) is True
    assert bool(_row(df, "NAME")["approved"]) is False
    assert bool(_row(df, "MODE_COL")["approved"]) is False


@pytest.fixture
def union_config():
    """Save/restore the config knobs the union query builder reads."""
    orig = {
        "STRUCTURE_DATABASES": list(config.STRUCTURE_DATABASES),
        "DATABASE_ALLOWLIST": list(config.DATABASE_ALLOWLIST),
    }
    yield
    config.STRUCTURE_DATABASES = orig["STRUCTURE_DATABASES"]
    config.DATABASE_ALLOWLIST = orig["DATABASE_ALLOWLIST"]


def test_information_schema_union_query_builds_union_all(union_config):
    config.STRUCTURE_DATABASES = ["FINANCE_DB", "HR_DB", "SALES_DB"]
    config.DATABASE_ALLOWLIST = []
    query = data._build_information_schema_union_query()
    assert query.count("UNION ALL") == 2
    for db in ["FINANCE_DB", "HR_DB", "SALES_DB"]:
        assert f"FROM {db}.INFORMATION_SCHEMA.COLUMNS" in query
    assert "TABLE_SCHEMA <> 'INFORMATION_SCHEMA'" in query


def test_information_schema_union_query_empty_list_raises(union_config):
    config.STRUCTURE_DATABASES = []
    config.DATABASE_ALLOWLIST = []
    with pytest.raises(ValueError, match="STRUCTURE_DATABASES is empty"):
        data._build_information_schema_union_query()


def test_information_schema_union_query_rejects_bad_identifier(union_config):
    config.STRUCTURE_DATABASES = ["FINANCE_DB", "DROP TABLE FOO; --"]
    config.DATABASE_ALLOWLIST = []
    with pytest.raises(ValueError, match="invalid database name"):
        data._build_information_schema_union_query()


def test_information_schema_union_query_intersects_allowlist(union_config):
    config.STRUCTURE_DATABASES = ["FINANCE_DB", "HR_DB", "SALES_DB"]
    config.DATABASE_ALLOWLIST = ["HR_DB"]
    query = data._build_information_schema_union_query()
    assert "HR_DB.INFORMATION_SCHEMA" in query
    assert "FINANCE_DB.INFORMATION_SCHEMA" not in query
    assert "SALES_DB.INFORMATION_SCHEMA" not in query
    assert "UNION ALL" not in query


def test_information_schema_union_query_allowlist_excludes_all_raises(union_config):
    config.STRUCTURE_DATABASES = ["FINANCE_DB", "HR_DB"]
    config.DATABASE_ALLOWLIST = ["SOME_OTHER_DB"]
    with pytest.raises(ValueError, match="excludes every database"):
        data._build_information_schema_union_query()


# ─────────────────────────────────────────────────────────────────────────────
# Usage layer (Layer 3 — "who reads this column")
# ─────────────────────────────────────────────────────────────────────────────

def test_usage_disabled_gives_empty_consumers(fixture_dir):
    config.USAGE_ENABLED = False
    df, health = data._build_catalog_and_health()
    assert (df["consumers"].map(len) == 0).all()
    assert health["usage_status"] == "disabled"
    assert health["usage_enabled"] is False


def test_usage_missing_source_degrades_gracefully(fixture_dir):
    # fixture_dir points USAGE_LOCAL_CSV at a path that doesn't exist.
    df, health = data._build_catalog_and_health()
    assert (df["consumers"].map(len) == 0).all()
    assert health["usage_status"].startswith("unavailable")
    # The rest of the catalog still loads normally — no crash, no missing rows.
    assert len(df) == 4


def test_usage_empty_source_is_graceful(fixture_dir):
    pd.DataFrame(columns=["column_name", "consumer_name", "consumer_type"]).to_csv(
        config.USAGE_LOCAL_CSV["path"], index=False
    )
    df, health = data._build_catalog_and_health()
    assert (df["consumers"].map(len) == 0).all()
    assert health["usage_status"] == "empty"


def test_usage_aggregates_and_dedups_consumers(fixture_dir):
    usage_df = pd.DataFrame([
        # appA reads SHARED_ID via two different tables -> should dedup to
        # ONE consumer entry: query_count summed, last_used = the later date.
        {"column_name": "SHARED_ID", "table": "DB1.PUBLIC.TABLE_A", "consumer_name": "appA",
         "consumer_type": "Streamlit app", "last_used": "2024-01-01", "query_count": 100},
        {"column_name": "SHARED_ID", "table": "DB1.PUBLIC.TABLE_B", "consumer_name": "appA",
         "consumer_type": "Streamlit app", "last_used": "2024-06-01", "query_count": 50},
        {"column_name": "SHARED_ID", "table": "DB2.PUBLIC.TABLE_C", "consumer_name": "dbtJob",
         "consumer_type": "dbt model", "last_used": "2024-03-01", "query_count": 20},
        {"column_name": "NAME", "table": "DB1.PUBLIC.TABLE_A", "consumer_name": "someUser",
         "consumer_type": "User / ad-hoc", "last_used": "2024-02-01", "query_count": 5},
    ])
    usage_df.to_csv(config.USAGE_LOCAL_CSV["path"], index=False)

    df, health = data._build_catalog_and_health()
    assert health["usage_status"] == "ok"
    assert health["usage_row_count"] == 4

    shared = _row(df, "SHARED_ID")
    consumers = shared["consumers"]
    assert len(consumers) == 2  # appA deduped across two tables, dbtJob separate

    by_name = {c["name"]: c for c in consumers}
    assert by_name["appA"]["query_count"] == 150
    assert by_name["appA"]["last_used"] == "2024-06-01"
    assert by_name["appA"]["type"] == "Streamlit app"
    assert by_name["dbtJob"]["query_count"] == 20

    # Sorted by query_count descending.
    assert consumers[0]["name"] == "appA"

    name_row = _row(df, "NAME")
    assert len(name_row["consumers"]) == 1
    assert name_row["consumers"][0]["name"] == "someUser"

    mode_row = _row(df, "MODE_COL")
    assert mode_row["consumers"] == []


def test_consumers_field_in_canonical_contract():
    assert "consumers" in data.CANONICAL_FIELDS
    assert data.CANONICAL_FIELDS[-1] == "consumers"
