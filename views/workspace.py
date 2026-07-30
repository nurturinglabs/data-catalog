"""
views/workspace.py — the Documentation workspace: the authoring/write side
of the descriptions the Catalog page reads. A coordinator assigns columns to
people; people fill in and submit descriptions; the coordinator approves.

The grid joins two config-driven sources (see config.py's Layer 5) via
workflow.load_workflow(): Source 1, a live structure+description query
(data_product/schema/N tables/"Description (live)", read-only), and
Source 2, an independently curated descriptions/approval feed
("Description (curated)", the editable field — saved via
workflow.save_curated_description). Assigned to/Status stay the workflow
table's own (Layer 4) — Source 2's approved flag only feeds the *displayed*
Status, it doesn't replace it. This is a separate store from
config.DESCRIPTIONS_SOURCE (still "workflow_table", still feeding the
Catalog page) — the two don't currently share data.

Depends on workflow.py (all reads/writes) + config. Never reference a
concrete data source, path, table name, or credential here — that lives in
config.py.
"""

import pandas as pd
import streamlit as st

import config
import theme
import workflow

# Columns used in only one table are excluded (mirrors the same business
# rule catalog.py applies) — not interesting for documentation effort
# focused on shared/reused columns across the warehouse. Manual/glossary
# rows (no physical table by design) and orphaned rows (kept for cleanup
# review regardless of their now-stale table_count) are exempt.
MIN_TABLE_COUNT = 2


def render() -> None:
    theme.header(nav_items=theme.NAV_ITEMS)

    # ─────────────────────────────────────────────────────────────────────────────
    # Role switch + identity — one aligned row. Role is the prominent
    # control (a segmented pill, same navy-active/outlined-inactive
    # language as every other toggle in this app); identity is a compact,
    # clearly-labeled picker beside it — not a full-width dropdown, since
    # it's a local dev stand-in, not the main decision being made here.
    # ─────────────────────────────────────────────────────────────────────────────

    st.session_state.setdefault("workspace_role", "Coordinator")
    workflow_df = workflow.load_workflow()
    workflow_df = workflow_df[
        (workflow_df["origin"] == "manual")
        | workflow_df["orphaned"]
        | (workflow_df["table_count"] >= MIN_TABLE_COUNT)
    ].reset_index(drop=True)

    # role_col/identity_col are kept tight (not proportionally generous)
    # so the pills and the picker sit close together, reading as one
    # control line — a wide column here just leaves dead space between
    # them, since neither the pills (which size to their own text) nor a
    # narrower selectbox column stretch to fill unclaimed room the way the
    # eye expects. progress_col absorbs the freed-up width; its own text
    # is right-aligned within it, so extra room there is harmless.
    # role_col is a bit wider than the absolute minimum as a safety
    # margin — the role pills' own CSS (role-toggle-scope) also carries a
    # 120px min-width per button regardless, so "Coordinator" can't wrap
    # even if this column ends up narrower on a smaller viewport.
    role_col, identity_col, progress_col = st.columns([2.0, 1.8, 4.4])
    with role_col:
        def _pick_role(value: str) -> None:
            st.session_state["workspace_role"] = value

        theme.pill_row(
            "workspace_role_tab", ["Coordinator", "Assignee"],
            st.session_state["workspace_role"], _pick_role,
            scope="role-toggle-scope",
        )
    with identity_col:
        if not workflow.is_sis():
            assignees = list(config.WORKFLOW_ASSIGNEES)
            current = workflow.current_user()
            default_index = assignees.index(current) if current in assignees else 0
            picked = st.selectbox(
                "👤 Viewing as", assignees, index=default_index, key="workspace_user_picker",
            )
            workflow.set_local_user(picked)
            st.caption(
                "Local stand-in — resolves via `CURRENT_USER()` on Snowflake."
            )

    actor = workflow.current_user()
    role = st.session_state["workspace_role"]

    with progress_col:
        if role == "Coordinator":
            bits = []
            for person in config.WORKFLOW_ASSIGNEES:
                person_df = workflow_df[workflow_df["assigned_to"] == person]
                total = len(person_df)
                done = int((person_df["status"] == "Approved").sum())
                bits.append(f"{person} {done}/{total}" if total else f"{person} —")
            bits.append(f"Unassigned {int((workflow_df['status'] == 'Unassigned').sum())}")
            st.markdown(
                f'<div style="text-align:right; font-size:12.5px; color:#64748B; '
                f'padding-top:0.6rem;">{" · ".join(bits)}</div>',
                unsafe_allow_html=True,
            )


    # ─────────────────────────────────────────────────────────────────────────────
    # Coordinator view — management console
    # ─────────────────────────────────────────────────────────────────────────────

    def render_coordinator(df: pd.DataFrame) -> None:
        filter_cols = st.columns([1.4, 1.2, 1.2, 0.9, 1.1, 1.2])
        with filter_cols[0]:
            status_filter = theme.safe_multiselect(
                "Status", workflow.STATUSES, placeholder="All statuses", key="coord_status_filter",
            )
        with filter_cols[1]:
            product_filter = st.selectbox(
                "Data product", ["All products"] + list(config.STRUCTURE_DATABASES),
                key="coord_product_filter",
            )
        with filter_cols[2]:
            assignee_filter = st.selectbox(
                "Assignee", ["Everyone", "Unassigned"] + list(config.WORKFLOW_ASSIGNEES),
                key="coord_assignee_filter",
            )
        with filter_cols[3]:
            # Nudged down to align with the selectboxes' input controls,
            # which sit below a label row these controls don't have.
            st.markdown('<div style="height: 1.9rem"></div>', unsafe_allow_html=True)
            orphaned_only = st.checkbox("Orphaned only", key="coord_orphaned_filter")
        with filter_cols[4]:
            st.markdown('<div style="height: 1.9rem"></div>', unsafe_allow_html=True)
            with theme.safe_popover("➕ Add row"):
                with st.form("add_row_form", clear_on_submit=True):
                    new_col = st.text_input("Column name")
                    new_product = st.selectbox("Data product", config.STRUCTURE_DATABASES)
                    new_table = st.text_input("Table (optional)")
                    if theme.action_form_submit_button("Add row", primary=True):
                        try:
                            workflow.add_manual_row(new_col, new_product, new_table, actor=actor)
                            st.toast(f"Added '{new_col.strip().upper()}'.", icon="✅")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

        filtered = df
        if status_filter:
            filtered = filtered[filtered["status"].isin(status_filter)]
        if product_filter != "All products":
            filtered = filtered[filtered["data_product"].str.contains(product_filter, regex=False)]
        if assignee_filter == "Unassigned":
            filtered = filtered[filtered["assigned_to"] == ""]
        elif assignee_filter != "Everyone":
            filtered = filtered[filtered["assigned_to"] == assignee_filter]
        if orphaned_only:
            filtered = filtered[filtered["orphaned"]]
        filtered = filtered.sort_values("column_name").reset_index(drop=True)

        # Filled in now rather than up in the filter_cols block above,
        # since the CSV needs `filtered` — which depends on the other
        # filter widgets' values — but the column slot itself was already
        # laid out alongside them, so it still reads as part of that row.
        with filter_cols[5]:
            st.markdown('<div style="height: 1.9rem"></div>', unsafe_allow_html=True)
            st.download_button(
                "⬇️ Download CSV",
                data=filtered.to_csv(index=False).encode("utf-8"),
                file_name="documentation_workspace.csv",
                mime="text/csv",
                key="coord_download_csv",
                use_container_width=True,
            )

        total = len(filtered)
        approved_n = int((filtered["status"] == "Approved").sum())
        unassigned_n = int((filtered["status"] == "Unassigned").sum())
        in_progress_n = int((filtered["status"] == "In progress").sum())
        submitted_n = int((filtered["status"] == "Submitted").sum())
        coverage_pct = (approved_n / total * 100) if total else 0.0

        theme.coverage_strip(coverage_pct, {
            "Unassigned": unassigned_n, "In progress": in_progress_n,
            "Submitted": submitted_n, "Approved": approved_n,
        })

        st.write("")
        if filtered.empty:
            st.info("No rows match the current filters.")
            return

        display = filtered.copy()
        display.insert(0, "Select", False)
        display["Column"] = display.apply(
            lambda r: r["column_name"]
            + (" · manual" if r["origin"] == "manual" else "")
            + (" · orphaned" if r["orphaned"] else ""),
            axis=1,
        )
        # Schema rides along as a compact suffix on Data product rather than
        # a literal second line — data_editor cells are plain text, no
        # sublines — since N tables/data product are both schema-derived
        # from the same query (Source 1) now.
        display["Data product"] = display.apply(
            lambda r: r["data_product"] + (f" · {r['schema']}" if r["schema"] else ""),
            axis=1,
        )
        display = display.rename(columns={
            "table_count": "N tables", "assigned_to": "Assigned to", "status": "Status",
            "description_curated": "Description (curated)", "description_live": "Description (live)",
        })
        display_cols = [
            "Select", "Column", "Data product", "N tables", "Assigned to", "Status",
            "Description (curated)", "Description (live)",
        ]

        # The grid lives in a bordered card (.st-key-coordinator-dock); the
        # bulk-action bar right after it is pinned to the bottom of the
        # viewport via CSS (position:fixed — see theme.py) so Assign/
        # Approve/Save stay reachable no matter how far down a long grid
        # the coordinator has scrolled, instead of stranded at the very
        # bottom of the page.
        dock = theme.safe_container(key="coordinator-dock")
        with dock:
            edited = st.data_editor(
                display[display_cols],
                hide_index=True,
                use_container_width=True,
                height=420,
                key="coordinator_grid",
                # "Description (live)" is read-only by design — Source 1's
                # own value, shown for reference only.
                disabled=["Column", "Data product", "N tables", "Status", "Description (live)"],
                column_config={
                    "Description (curated)": st.column_config.TextColumn(width="large"),
                    "Description (live)": st.column_config.TextColumn(
                        width="large", help="Read-only — the live structure query's own description.",
                    ),
                    "Assigned to": st.column_config.SelectboxColumn(
                        options=[""] + list(config.WORKFLOW_ASSIGNEES),
                    ),
                },
            )

            selected_mask = edited["Select"].to_numpy()
            selected_columns = filtered.loc[selected_mask, "column_name"].tolist()
            selected_updated_at = dict(zip(filtered.loc[selected_mask, "column_name"], filtered.loc[selected_mask, "updated_at"]))

            action_bar = theme.safe_container(key="coordinator-action-bar")
        with action_bar:
            count_col, assignee_col, assign_col, approve_col, spacer_col, save_col = st.columns(
                [1.5, 1.6, 1, 1, 2.4, 1.6]
            )
            with count_col:
                st.markdown(
                    f'<div style="padding-top:0.5rem; font-size:13px; font-weight:600; color:#475569;">'
                    f'{len(selected_columns)} selected</div>',
                    unsafe_allow_html=True,
                )
            with assignee_col:
                assignee_choice = st.selectbox(
                    "Assign to", config.WORKFLOW_ASSIGNEES, key="coord_bulk_assignee", label_visibility="collapsed",
                )
            with assign_col:
                if theme.action_button("Assign", key="coord_bulk_assign_btn", primary=True, use_container_width=True):
                    if not selected_columns:
                        st.warning("Select at least one row first.")
                    else:
                        edits = [
                            {"column_name": c, "assigned_to": assignee_choice, "status": "Assigned",
                             "_expected_updated_at": selected_updated_at[c]}
                            for c in selected_columns
                        ]
                        try:
                            workflow.save_rows(edits, actor=actor)
                            st.toast(f"Assigned {len(selected_columns)} column(s) to {assignee_choice}.", icon="✅")
                            st.rerun()
                        except workflow.WorkflowConflictError as exc:
                            st.error(f"{exc} Reload to see the latest version before retrying.")
            with approve_col:
                if theme.action_button("Approve", key="coord_bulk_approve_btn", primary=True, use_container_width=True):
                    submittable = filtered[
                        filtered["column_name"].isin(selected_columns) & (filtered["status"] == "Submitted")
                    ]
                    skipped = len(selected_columns) - len(submittable)
                    if submittable.empty:
                        st.warning("No selected rows are in 'Submitted' status.")
                    else:
                        edits = [
                            {"column_name": c, "status": "Approved", "_expected_updated_at": u}
                            for c, u in zip(submittable["column_name"], submittable["updated_at"])
                        ]
                        try:
                            workflow.save_rows(edits, actor=actor)
                            msg = f"Approved {len(submittable)} column(s)."
                            if skipped:
                                msg += f" Skipped {skipped} not in 'Submitted' status."
                            st.toast(msg, icon="✅")
                            st.rerun()
                        except workflow.WorkflowConflictError as exc:
                            st.error(f"{exc} Reload to see the latest version before retrying.")
            with save_col:
                if st.button("💾 Save edits", key="coord_save_desc_btn", use_container_width=True):
                    # Curated description edits and assignment edits now go
                    # to two different stores: Description (curated) is
                    # Source 2 (an independent curated feed, no updated_at
                    # of its own to conflict-check against — see
                    # save_curated_description); Assigned to stays exactly
                    # as before, in COLUMN_ASSIGNMENTS via save_rows, with
                    # its existing optimistic-concurrency check.
                    orig_curated = filtered["description_curated"].astype(str).to_numpy()
                    new_curated = edited["Description (curated)"].astype(str).to_numpy()
                    curated_changed = orig_curated != new_curated

                    orig_assignee = filtered["assigned_to"].astype(str).to_numpy()
                    new_assignee = edited["Assigned to"].astype(str).to_numpy()
                    assignee_changed = orig_assignee != new_assignee

                    if not (curated_changed.any() or assignee_changed.any()):
                        st.info("No changes to save.")
                    else:
                        for i in filtered.index[curated_changed]:
                            workflow.save_curated_description(
                                filtered.at[i, "column_name"], edited.at[i, "Description (curated)"],
                            )

                        assignee_edits = []
                        for i in filtered.index[assignee_changed]:
                            new_person = edited.at[i, "Assigned to"]
                            edit = {
                                "column_name": filtered.at[i, "column_name"],
                                "assigned_to": new_person,
                                "_expected_updated_at": filtered.at[i, "updated_at"],
                            }
                            # Picking someone for a previously-Unassigned
                            # row also claims it; reassigning a row already
                            # in progress leaves its status alone (not a
                            # fresh assignment).
                            if filtered.at[i, "status"] == "Unassigned" and new_person:
                                edit["status"] = "Assigned"
                            assignee_edits.append(edit)

                        try:
                            if assignee_edits:
                                workflow.save_rows(assignee_edits, actor=actor)
                            parts = []
                            if curated_changed.any():
                                parts.append(f"{int(curated_changed.sum())} description edit(s)")
                            if assignee_edits:
                                parts.append(f"{len(assignee_edits)} assignment(s)")
                            st.toast(f"Saved {', '.join(parts)}.", icon="✅")
                            st.rerun()
                        except workflow.WorkflowConflictError as exc:
                            st.error(f"{exc} Reload to see the latest version before retrying.")

        # The action bar above is position:fixed to the viewport bottom, so
        # it no longer occupies flow space of its own — without this, its
        # ~70px would sit on top of whatever the page's actual last content
        # happens to be.
        st.markdown('<div style="height: 76px"></div>', unsafe_allow_html=True)


    # ─────────────────────────────────────────────────────────────────────────────
    # Assignee view — focused work queue
    # ─────────────────────────────────────────────────────────────────────────────

    def render_assignee(df: pd.DataFrame, actor: str) -> None:
        st.markdown(f"##### My queue — {actor}")

        my_open = df[(df["assigned_to"] == actor) & (df["status"].isin(workflow.OPEN_STATUSES))]
        my_open = my_open.sort_values("column_name").reset_index(drop=True)

        if my_open.empty:
            st.success("Nothing open in your queue right now.")
            return

        st.caption(f"{len(my_open)} column{'s' if len(my_open) != 1 else ''} open")

        for _, row in my_open.iterrows():
            col = row["column_name"]
            tables = row["tables"]  # Source 1, already resolved per-row by load_workflow()
            label = f"{col} — {row['data_product']} ({len(tables)} table{'s' if len(tables) != 1 else ''})"
            with st.expander(label):
                if tables:
                    st.caption("Appears in: " + ", ".join(tables))
                elif row["origin"] == "manual":
                    st.caption("Manual / glossary entry — no physical table.")
                if row["description_live"]:
                    st.caption(f"Live (from structure query): {row['description_live']}")

                draft_key = f"assignee_draft_{col}"
                st.session_state.setdefault(draft_key, row["description_curated"])
                st.text_area("Description", key=draft_key, height=100, label_visibility="collapsed")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Save draft", key=f"save_draft_{col}", use_container_width=True):
                        try:
                            workflow.save_curated_description(col, st.session_state[draft_key])
                            workflow.save_rows([{
                                "column_name": col,
                                "status": "In progress",
                                "_expected_updated_at": row["updated_at"],
                            }], actor=actor)
                            st.toast("Draft saved.", icon="✅")
                            st.rerun()
                        except workflow.WorkflowConflictError as exc:
                            st.error(f"{exc} Reload to see the latest version before retrying.")
                with c2:
                    if theme.action_button("Submit", key=f"submit_{col}", primary=True, use_container_width=True):
                        if not st.session_state[draft_key].strip():
                            st.warning("Write a description before submitting.")
                        else:
                            try:
                                workflow.save_curated_description(col, st.session_state[draft_key])
                                workflow.save_rows([{
                                    "column_name": col,
                                    "status": "Submitted",
                                    "_expected_updated_at": row["updated_at"],
                                }], actor=actor)
                                st.toast("Submitted for review.", icon="✅")
                                st.rerun()
                            except workflow.WorkflowConflictError as exc:
                                st.error(f"{exc} Reload to see the latest version before retrying.")


    if role == "Coordinator":
        render_coordinator(workflow_df)
    else:
        render_assignee(workflow_df, actor)

