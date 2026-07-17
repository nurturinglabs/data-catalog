"""
app.py — the UI. Depends only on data.load_catalog() + config. Never
reference a concrete data source, path, table name, or credential here —
that all lives in config.py.
"""

import math

import streamlit as st

import config
import data
import theme

ALL_DATABASES = "All databases"
ALL_SCHEMAS = "All schemas"
PAGE_SIZES = [25, 50, 100]

st.set_page_config(
    page_title=f"{config.APP_TITLE}",
    page_icon="📚",
    layout="wide",
)

theme.inject_css()

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

try:
    catalog_df = data.load_catalog()
except (ValueError, data.DataSourceError) as exc:
    st.error(f"Could not load the catalog: {exc}")
    st.stop()

catalog_df = catalog_df.reset_index(drop=True)
catalog_df["_row_id"] = catalog_df.index

all_databases = sorted({db for row in catalog_df["databases"] for db in row})
all_schemas_by_db: dict = {}
for row in catalog_df["schemas"]:
    for schema_fqn in row:
        db = schema_fqn.split(".")[0]
        all_schemas_by_db.setdefault(db, set()).add(schema_fqn)

# ─────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ─────────────────────────────────────────────────────────────────────────────

st.session_state.setdefault("selected_db", ALL_DATABASES)
st.session_state.setdefault("selected_schema", ALL_SCHEMAS)
st.session_state.setdefault("documented_only", False)
st.session_state.setdefault("page", 1)

# ─────────────────────────────────────────────────────────────────────────────
# Header band
# ─────────────────────────────────────────────────────────────────────────────

theme.header()

# ─────────────────────────────────────────────────────────────────────────────
# Browse databases & schemas — a native st.expander. This is the simplest,
# most reliable way to give a section its own click-to-hide/show affordance:
# Streamlit owns the expand/collapse state and the chevron natively, so
# there's no custom CSS or session-state toggle to fight with (unlike a
# CSS-collapsed st.sidebar, which can end up fighting Streamlit's own
# internal layout/resize handling for that element).
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("🔍  Browse databases & schemas", expanded=False):
    theme.scope_marker("rail-scope")

    all_active = st.session_state["selected_db"] == ALL_DATABASES
    if theme.toggle_button("All databases", key="nav_all", active=all_active, use_container_width=False):
        st.session_state["selected_db"] = ALL_DATABASES
        st.session_state["selected_schema"] = ALL_SCHEMAS
        st.rerun()

    if all_databases:
        db_cols = st.columns(len(all_databases))
        for db_col, db in zip(db_cols, all_databases):
            with db_col:
                db_active = (
                    st.session_state["selected_db"] == db
                    and st.session_state["selected_schema"] == ALL_SCHEMAS
                )
                if theme.toggle_button(db, key=f"nav_db_{db}", active=db_active):
                    st.session_state["selected_db"] = db
                    st.session_state["selected_schema"] = ALL_SCHEMAS
                    st.rerun()

                for schema_fqn in sorted(all_schemas_by_db.get(db, [])):
                    schema_active = st.session_state["selected_schema"] == schema_fqn
                    schema_short = schema_fqn.split(".", 1)[1]
                    if theme.toggle_button(
                        f"  {schema_short}",
                        key=f"nav_schema_{schema_fqn}", active=schema_active,
                    ):
                        st.session_state["selected_db"] = db
                        st.session_state["selected_schema"] = schema_fqn
                        st.rerun()

    st.markdown("---")
    if st.button("🔄 Refresh data"):
        data.clear_cache()
        st.rerun()

selected_db = st.session_state["selected_db"]
selected_schema = st.session_state["selected_schema"]
documented_only = st.session_state["documented_only"]
search_text = st.session_state.get("search_text", "")

# ─────────────────────────────────────────────────────────────────────────────
# Apply filters
# ─────────────────────────────────────────────────────────────────────────────

filtered_df = catalog_df

if search_text:
    needle = search_text.lower()
    mask = (
        filtered_df["column_name"].str.lower().str.contains(needle, regex=False)
        | filtered_df["description"].str.lower().str.contains(needle, regex=False)
    )
    filtered_df = filtered_df[mask]

if selected_db != ALL_DATABASES:
    filtered_df = filtered_df[filtered_df["databases"].map(lambda lst: selected_db in lst)]

if selected_schema != ALL_SCHEMAS:
    filtered_df = filtered_df[filtered_df["schemas"].map(lambda lst: selected_schema in lst)]

if documented_only:
    filtered_df = filtered_df[filtered_df["documented"]]

filtered_df = filtered_df.reset_index(drop=True)

filters_signature = (search_text, selected_db, selected_schema, documented_only)
if st.session_state.get("_filters_signature") != filters_signature:
    st.session_state["_filters_signature"] = filters_signature
    st.session_state["page"] = 1

if selected_schema != ALL_SCHEMAS:
    scope_label = selected_schema
elif selected_db != ALL_DATABASES:
    scope_label = selected_db
else:
    scope_label = "All databases"

# ─────────────────────────────────────────────────────────────────────────────
# Coverage metrics (reflect the filtered view)
# ─────────────────────────────────────────────────────────────────────────────

view_count = len(filtered_df)
documented_count = int(filtered_df["documented"].sum())

if view_count:
    busiest = filtered_df.loc[filtered_df["tables"].map(len).idxmax()]
    busiest_value = f"{busiest['column_name']} ({len(busiest['tables'])})"
else:
    busiest_value = "—"

theme.kpi_row([
    {"label": "Number of Columns", "value": f"{view_count}"},
    {"label": "Columns with Descriptions", "value": f"{documented_count}"},
    {"label": "Column used in most tables", "value": busiest_value},
])

# ─────────────────────────────────────────────────────────────────────────────
# Search (left) + documented filter pills (right) — below the KPIs, same row
# ─────────────────────────────────────────────────────────────────────────────

with st.container():
    theme.scope_marker("tags-scope")
    row_cols = st.columns([3, 1, 2, 4])
    with row_cols[0]:
        st.text_input(
            "Search", placeholder="🔍 Search columns or descriptions",
            label_visibility="collapsed", key="search_text",
        )
    with row_cols[1]:
        if theme.toggle_button("All", key="filter_all", active=not documented_only, use_container_width=False):
            st.session_state["documented_only"] = False
            st.rerun()
    with row_cols[2]:
        if theme.toggle_button(
            "With Descriptions", key="filter_documented",
            active=documented_only, use_container_width=False,
        ):
            st.session_state["documented_only"] = True
            st.rerun()

st.write("")
results_col, detail_col = st.columns([3, 2], gap="medium")

# ─────────────────────────────────────────────────────────────────────────────
# Results (left column) — cards + pagination
# ─────────────────────────────────────────────────────────────────────────────

with results_col:
    header_row = st.columns([3, 1])
    with header_row[0]:
        st.caption(f"{scope_label} — {view_count} column{'s' if view_count != 1 else ''}")
    with header_row[1]:
        page_size = st.selectbox(
            "Page size", PAGE_SIZES, index=0, key="page_size", label_visibility="collapsed",
        )

    total = len(filtered_df)
    n_pages = max(1, math.ceil(total / page_size))
    page = min(st.session_state.get("page", 1), n_pages)

    start = (page - 1) * page_size
    end = min(start + page_size, total)
    page_df = filtered_df.iloc[start:end]

    selected_row_id = st.session_state.get("selected_row_id")

    if page_df.empty:
        st.info("No matching columns.")
    else:
        display_df = page_df.copy()
        display_df["Column name"] = display_df["column_name"]
        display_df["Has description"] = display_df["documented"]
        display_df["Approved"] = display_df["tags"].map(
            lambda tags: any(t.strip().lower() == "certified" for t in tags)
        )
        display_df["# Tables"] = display_df["tables"].map(len)
        display_cols = ["Column name", "Has description", "Approved", "# Tables"]

        try:
            event = st.dataframe(
                display_df[display_cols],
                use_container_width=True,
                hide_index=True,
                height=480,
                on_select="rerun",
                selection_mode="single-row",
                key=f"results_table_{page}_{page_size}",
            )
            selected_positions = getattr(getattr(event, "selection", None), "rows", [])
            if selected_positions:
                selected_row_id = page_df.iloc[selected_positions[0]]["_row_id"]
                st.session_state["selected_row_id"] = selected_row_id
        except TypeError:
            # Older Streamlit without on_select/selection_mode support —
            # degrade to a selectbox of the current page's columns.
            st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True, height=480)
            options = page_df["column_name"].tolist()
            if options:
                choice = st.selectbox(
                    "Select a column for detail", options, key=f"fallback_select_{page}",
                )
                selected_row_id = page_df[page_df["column_name"] == choice].iloc[0]["_row_id"]
                st.session_state["selected_row_id"] = selected_row_id

    st.caption(f"Showing {start + 1}-{end} of {total}" if total else "No matching columns")

    nav = st.columns([1, 4, 1])
    with nav[0]:
        if st.button("← Prev", disabled=page <= 1):
            st.session_state["page"] = page - 1
            st.rerun()
    with nav[2]:
        if st.button("Next →", disabled=page >= n_pages):
            st.session_state["page"] = page + 1
            st.rerun()

    # st.markdown("##### Export")
    # export_df = filtered_df.drop(columns=["_row_id"]).copy()
    # for list_col in ("tags", "tables", "databases", "schemas"):
    #     export_df[list_col] = export_df[list_col].map(lambda lst: ", ".join(lst))
    # csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    # st.download_button(
    #     "⬇ Download view (CSV)",
    #     data=csv_bytes,
    #     file_name="data_catalog_export.csv",
    #     mime="text/csv",
    # )

# ─────────────────────────────────────────────────────────────────────────────
# Detail (right column)
# ─────────────────────────────────────────────────────────────────────────────

with detail_col:
    st.markdown("##### Column detail")
    detail_row = None
    if selected_row_id is not None:
        match = filtered_df[filtered_df["_row_id"] == selected_row_id]
        if len(match):
            detail_row = match.iloc[0]
    if detail_row is None and len(filtered_df):
        detail_row = filtered_df.iloc[0]

    if detail_row is None:
        st.info("No column selected.")
    else:
        theme.render_detail_card(detail_row)

# # ─────────────────────────────────────────────────────────────────────────────
# # Catalog health panel
# # ─────────────────────────────────────────────────────────────────────────────

# with st.expander("📋 Catalog health"):
#     health = data.load_health()
#     h1, h2 = st.columns(2)
#     with h1:
#         st.markdown(f"**Descriptions source:** `{health['descriptions_source']}`")
#         st.markdown(f"**Descriptions rows:** {health['descriptions_row_count']}")
#         st.markdown(f"**Headers found:** {health['descriptions_headers_found']}")
#         st.markdown(f"**Missing optional headers:** {health['descriptions_headers_missing_optional'] or 'none'}")
#         st.markdown(f"**Join grain:** `{health['join_grain']}`")
#         st.markdown(f"**Catalog spine:** `{health['catalog_spine']}`")
#     with h2:
#         st.markdown(f"**Structure source:** `{health['structure_source']}`")
#         st.markdown(f"**Structure rows:** {health['structure_row_count']}")
#         st.markdown(f"**Headers found:** {health['structure_headers_found']}")
#         st.markdown(f"**Database allowlist:** {health['database_allowlist'] or 'none (unrestricted)'}")
#         st.markdown(f"**Entries / coverage:** {health['entry_count']} / {health['coverage_pct']:.1f}%")
#         st.markdown(f"**Last refresh:** {health['last_refresh']}")

#     if health["structure_truncated"]:
#         st.warning(
#             f"Structure pull exceeded MAX_STRUCTURE_ROWS "
#             f"({health['max_structure_rows']}) and was truncated. "
#             f"Narrow DATABASE_ALLOWLIST or raise the cap in config.py."
#         )
