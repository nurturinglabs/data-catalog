"""
views/catalog.py — the catalog (read) page, rendered via render(). Depends
only on data.load_catalog() + config. Never reference a concrete data
source, path, table name, or credential here — that all lives in config.py.
"""

import streamlit as st

import config
import data
import theme


def render() -> None:
    ALL_PRODUCTS = "All products"
    ALL_SCHEMAS = "All schemas"
    ALL_TABLES = "All tables"

    # Columns used in only one table are excluded (see the "used in most
    # tables" business rule) — not interesting for a catalog focused on
    # shared/reused columns across the warehouse.
    MIN_TABLE_COUNT = 2

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
    # Header band
    # ─────────────────────────────────────────────────────────────────────────────

    theme.header(nav_items=theme.NAV_ITEMS)

    # ─────────────────────────────────────────────────────────────────────────────
    # Product → Schema → Table drill-down. Single-select pills at each level; no
    # tabs — one shared view, filtered top-down. Picking a product resets
    # schema/table (their old selections may not even exist for the new
    # product); picking a schema resets table. Each level's pill options are
    # scoped to whatever's selected above it, and a level only renders once the
    # level above it has a specific (non-"All") selection.
    # ─────────────────────────────────────────────────────────────────────────────

    st.session_state.setdefault("selected_product", ALL_PRODUCTS)
    st.session_state.setdefault("selected_schema", ALL_SCHEMAS)
    st.session_state.setdefault("selected_table", ALL_TABLES)


    selected_product = st.session_state["selected_product"]
    selected_schema = st.session_state["selected_schema"]
    selected_table = st.session_state["selected_table"]

    # Product pills
    def _pick_product(value):
        st.session_state["selected_product"] = value
        st.session_state["selected_schema"] = ALL_SCHEMAS
        st.session_state["selected_table"] = ALL_TABLES


    theme.pill_row("product", [ALL_PRODUCTS] + list(config.STRUCTURE_DATABASES), selected_product, _pick_product)

    # Schema pills — only once a specific product is selected
    if selected_product != ALL_PRODUCTS:
        product_df = catalog_df[catalog_df["databases"].map(lambda lst: selected_product in lst)]
        schema_names = sorted({
            s.split(".", 1)[1]
            for row in product_df["schemas"] for s in row
            if s.startswith(f"{selected_product}.")
        })
        if schema_names:
            def _pick_schema(value):
                st.session_state["selected_schema"] = value
                st.session_state["selected_table"] = ALL_TABLES

            theme.pill_row("schema", [ALL_SCHEMAS] + schema_names, selected_schema, _pick_schema)

    # Table pills — only once a specific product AND schema are selected
    if selected_product != ALL_PRODUCTS and selected_schema != ALL_SCHEMAS:
        schema_fqn = f"{selected_product}.{selected_schema}"
        schema_df = catalog_df[catalog_df["schemas"].map(lambda lst: schema_fqn in lst)]
        table_names = sorted({
            t.rsplit(".", 1)[1]
            for row in schema_df["tables"] for t in row
            if t.startswith(f"{schema_fqn}.")
        })
        if table_names:
            def _pick_table(value):
                st.session_state["selected_table"] = value

            theme.pill_row("table", [ALL_TABLES] + table_names, selected_table, _pick_table)

    # Re-read — a pill click above already st.rerun()s, so these always reflect
    # the current selection by the time we get here.
    selected_product = st.session_state["selected_product"]
    selected_schema = st.session_state["selected_schema"]
    selected_table = st.session_state["selected_table"]

    # ─────────────────────────────────────────────────────────────────────────────
    # Apply the drill-down filter
    # ─────────────────────────────────────────────────────────────────────────────

    scoped_df = catalog_df
    if selected_product != ALL_PRODUCTS:
        scoped_df = scoped_df[scoped_df["databases"].map(lambda lst: selected_product in lst)]
    if selected_schema != ALL_SCHEMAS:
        schema_fqn = f"{selected_product}.{selected_schema}"
        scoped_df = scoped_df[scoped_df["schemas"].map(lambda lst: schema_fqn in lst)]
    if selected_table != ALL_TABLES:
        table_fqn = f"{selected_product}.{selected_schema}.{selected_table}"
        scoped_df = scoped_df[scoped_df["tables"].map(lambda lst: table_fqn in lst)]

    if selected_table != ALL_TABLES:
        scope_label = f"{selected_product}.{selected_schema}.{selected_table}"
    elif selected_schema != ALL_SCHEMAS:
        scope_label = f"{selected_product}.{selected_schema}"
    elif selected_product != ALL_PRODUCTS:
        scope_label = selected_product
    else:
        scope_label = "All products"

    # ─────────────────────────────────────────────────────────────────────────────
    # Search — right above the results table
    # ─────────────────────────────────────────────────────────────────────────────

    search_text = st.session_state.get("search_text", "")

    df = scoped_df
    if search_text:
        needle = search_text.lower()
        mask = (
            df["column_name"].str.lower().str.contains(needle, regex=False)
            | df["description"].str.lower().str.contains(needle, regex=False)
        )
        df = df[mask]
    df = df.sort_values("column_name", kind="stable").reset_index(drop=True)

    # ─────────────────────────────────────────────────────────────────────────────
    # KPIs (reflect the current drill-down + search)
    # ─────────────────────────────────────────────────────────────────────────────

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
    results_col, detail_col = theme.safe_columns([3, 2], gap="medium")

    with results_col:
        st.caption(f"{scope_label} — {view_count} column{'s' if view_count != 1 else ''}")
        st.text_input(
            "Search", placeholder="🔍 Search columns or descriptions",
            label_visibility="collapsed", key="search_text",
        )

        selected_row_id = st.session_state.get("selected_row_id")

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
                    key="results_table",
                )
                selected_positions = getattr(getattr(event, "selection", None), "rows", [])
                if selected_positions:
                    selected_row_id = df.iloc[selected_positions[0]]["_row_id"]
                    st.session_state["selected_row_id"] = selected_row_id
            except TypeError:
                # Older Streamlit without on_select/selection_mode support —
                # degrade to a selectbox of the full (unpaginated) list.
                st.dataframe(display_df[display_cols], use_container_width=True, hide_index=True, height=560)
                options = df["column_name"].tolist()
                if options:
                    choice = st.selectbox("Select a column for detail", options, key="fallback_select")
                    selected_row_id = df[df["column_name"] == choice].iloc[0]["_row_id"]
                    st.session_state["selected_row_id"] = selected_row_id

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

