"""
app.py — the UI. Depends only on data.load_catalog() + config. Never
reference a concrete data source, path, table name, or credential here —
that all lives in config.py.
"""

import streamlit as st

import config
import data
import theme

# Sort options for the results table. st.dataframe's own column-header click
# sort is a frontend-only feature with no callback into Python, so it can
# only ever reorder whichever rows are currently loaded into the widget. To
# guarantee sorting always covers the *entire* result set (not just "the
# current page"), results are no longer paginated — the full filtered/sorted
# set is rendered into one scrollable table, so both this explicit control
# and clicking a column header operate on everything, not a subset.
SORT_OPTIONS = {
    "Column name": "column_name",
    "Data type": "data_type",
    "Has description": "documented",
    "Approved": "approved",
    "# Tables": "_table_count",
}

# Columns used in only one table are excluded from every tab (see the
# "used in most tables" business rule) — not interesting for a catalog
# focused on shared/reused columns across the warehouse.
MIN_TABLE_COUNT = 2

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

catalog_df = catalog_df[catalog_df["tables"].map(len) >= MIN_TABLE_COUNT]
catalog_df = catalog_df.reset_index(drop=True)
catalog_df["_row_id"] = catalog_df.index

# ─────────────────────────────────────────────────────────────────────────────
# Header band, with a Refresh button in the top-right corner
# ─────────────────────────────────────────────────────────────────────────────

header_action_col = theme.header()
with header_action_col:
    if st.button(
        "🔄 Refresh", key="header_refresh", use_container_width=True,
        help=(
            f"Data is cached for {config.CACHE_TTL_SECONDS // 60} minutes. "
            "Click after changing config.py to see it immediately."
        ),
    ):
        data.clear_cache()
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Per-tab filter row: search, documented-only, sort. Each tab gets its own
# independent copy (unique widget keys per tab_key), so searching within one
# database's tab doesn't affect any other tab.
# ─────────────────────────────────────────────────────────────────────────────

def render_filters(tab_key: str):
    with st.container():
        theme.scope_marker("tags-scope")
        row_cols = st.columns([3, 1, 2, 1, 1])
        with row_cols[0]:
            st.text_input(
                "Search", placeholder="🔍 Search columns or descriptions",
                label_visibility="collapsed", key=f"search_text_{tab_key}",
            )
        with row_cols[1]:
            active_all = not st.session_state.get(f"documented_only_{tab_key}", False)
            if theme.toggle_button(
                "All", key=f"filter_all_{tab_key}", active=active_all, use_container_width=False,
            ):
                st.session_state[f"documented_only_{tab_key}"] = False
                st.rerun()
        with row_cols[2]:
            active_doc = st.session_state.get(f"documented_only_{tab_key}", False)
            if theme.toggle_button(
                "With Descriptions", key=f"filter_documented_{tab_key}",
                active=active_doc, use_container_width=False,
            ):
                st.session_state[f"documented_only_{tab_key}"] = True
                st.rerun()
        with row_cols[3]:
            st.selectbox(
                "Sort by", list(SORT_OPTIONS.keys()),
                key=f"sort_by_{tab_key}", label_visibility="collapsed",
            )
        with row_cols[4]:
            st.selectbox(
                "Direction", ["Ascending", "Descending"],
                key=f"sort_dir_{tab_key}", label_visibility="collapsed",
            )

    return (
        st.session_state.get(f"search_text_{tab_key}", ""),
        st.session_state.get(f"documented_only_{tab_key}", False),
        st.session_state.get(f"sort_by_{tab_key}", "Column name"),
        st.session_state.get(f"sort_dir_{tab_key}", "Ascending") == "Ascending",
    )


def render_database_view(tab_key: str, base_df, scope_label: str) -> None:
    """Render this tab's own filter row, KPIs, results table, and detail
    panel for base_df (already scoped to this tab's database). tab_key must
    be unique per tab — st.tabs() renders every tab body on every rerun (not
    just the visible one), so widget keys across tabs would collide without
    this suffix on every one of them."""
    search_text, documented_only, sort_label, sort_ascending = render_filters(tab_key)

    df = base_df
    if search_text:
        needle = search_text.lower()
        mask = (
            df["column_name"].str.lower().str.contains(needle, regex=False)
            | df["description"].str.lower().str.contains(needle, regex=False)
        )
        df = df[mask]
    if documented_only:
        df = df[df["documented"]]

    sort_field = SORT_OPTIONS[sort_label]
    if sort_field == "_table_count":
        df = df.assign(_table_count=df["tables"].map(len))
    df = df.sort_values(sort_field, ascending=sort_ascending, kind="stable").reset_index(drop=True)

    view_count = len(df)
    documented_count = int(df["documented"].sum())
    if view_count:
        busiest = df.loc[df["tables"].map(len).idxmax()]
        busiest_value = f"{busiest['column_name']} ({len(busiest['tables'])})"
    else:
        busiest_value = "—"

    theme.kpi_row([
        {"label": "Number of Columns", "value": f"{view_count}", "icon": "📊", "accent": "primary"},
        {"label": "Columns with Descriptions", "value": f"{documented_count}", "icon": "📝", "accent": "primary"},
        {"label": "Column used in most tables", "value": busiest_value, "icon": "🔗", "accent": "yellow"},
    ])

    st.write("")
    results_col, detail_col = st.columns([3, 2], gap="medium")

    selected_key = f"selected_row_id_{tab_key}"

    with results_col:
        st.caption(f"{scope_label} — {view_count} column{'s' if view_count != 1 else ''}")

        selected_row_id = st.session_state.get(selected_key)

        if df.empty:
            st.info("No matching columns.")
        else:
            display_df = df.copy()
            display_df["Column name"] = display_df["column_name"]
            display_df["Has description"] = display_df["documented"]
            display_df["Approved"] = display_df["approved"]
            display_df["# Tables"] = display_df["tables"].map(len)
            display_cols = ["Column name", "Has description", "Approved", "# Tables"]

            try:
                event = st.dataframe(
                    display_df[display_cols],
                    use_container_width=True,
                    hide_index=True,
                    height=560,
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"results_table_{tab_key}",
                )
                selected_positions = getattr(getattr(event, "selection", None), "rows", [])
                if selected_positions:
                    selected_row_id = df.iloc[selected_positions[0]]["_row_id"]
                    st.session_state[selected_key] = selected_row_id
            except TypeError:
                # Older Streamlit without on_select/selection_mode support —
                # degrade to a selectbox of the full (unpaginated) list.
                st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True, height=560)
                options = df["column_name"].tolist()
                if options:
                    choice = st.selectbox(
                        "Select a column for detail", options, key=f"fallback_select_{tab_key}",
                    )
                    selected_row_id = df[df["column_name"] == choice].iloc[0]["_row_id"]
                    st.session_state[selected_key] = selected_row_id

    with detail_col:
        st.markdown("##### Column detail")
        detail_row = None
        if selected_row_id is not None:
            match = df[df["_row_id"] == selected_row_id]
            if len(match):
                detail_row = match.iloc[0]
        if detail_row is None and len(df):
            detail_row = df.iloc[0]

        if detail_row is None:
            st.info("No column selected.")
        else:
            usage_status = data.load_health().get("usage_status")
            theme.render_detail_card(detail_row, usage_status=usage_status)


# ─────────────────────────────────────────────────────────────────────────────
# Database tabs — "All" (optionally scoped to one or more databases) plus one
# tab per config.STRUCTURE_DATABASES entry. Never hardcoded — a database
# added to that config list picks up its own tab automatically. Styled (see
# theme.inject_css) to read as a continuation of the navy header band.
# ─────────────────────────────────────────────────────────────────────────────

tab_labels = ["All"] + list(config.STRUCTURE_DATABASES)
tabs = st.tabs(tab_labels)

with tabs[0]:
    selected_dbs = st.multiselect(
        "Filter to one or more databases (optional)",
        options=config.STRUCTURE_DATABASES,
        key="all_tab_databases",
    )
    all_df = catalog_df
    if selected_dbs:
        all_df = all_df[all_df["databases"].map(lambda lst: any(db in lst for db in selected_dbs))]
        scope_label = ", ".join(selected_dbs)
    else:
        scope_label = "All databases"
    render_database_view("all", all_df, scope_label)

for db in config.STRUCTURE_DATABASES:
    with tabs[tab_labels.index(db)]:
        db_df = catalog_df[catalog_df["databases"].map(lambda lst, db=db: db in lst)]
        render_database_view(db, db_df, db)
