"""
views/workspace.py — the Documentation workspace: the authoring/write side
of the descriptions the Catalog page reads. A coordinator assigns columns to
people; people fill in and submit descriptions; the coordinator approves.
Approved rows are the *same* table data.py reads descriptions from (see
config.DESCRIPTIONS_SOURCE == "workflow_table") — there is no separate
store, so an approval here shows up on the Catalog page immediately
(workflow.save_rows clears data's cache).

Depends on workflow.py (read/write) and data.py (live structure, for table
context) + config. Never reference a concrete data source, path, table
name, or credential here — that lives in config.py.
"""

import pandas as pd
import streamlit as st

import config
import data
import theme
import workflow


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

    role_col, identity_col, progress_col = st.columns([2.2, 2.6, 3.4])
    with role_col:
        def _pick_role(value: str) -> None:
            st.session_state["workspace_role"] = value

        theme.pill_row(
            "workspace_role_tab", ["Coordinator", "Assignee"],
            st.session_state["workspace_role"], _pick_role,
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
        display = display.rename(columns={
            "table_count": "N tables", "data_product": "Data product",
            "assigned_to": "Assigned to", "status": "Status", "description": "Description",
        })
        display_cols = ["Select", "Column", "N tables", "Data product", "Assigned to", "Status", "Description"]

        # The grid and the bulk-action bar are wrapped in one bordered card
        # (.st-key-coordinator-dock) so the actions read as attached to the
        # rows they operate on, instead of stranded at the page bottom.
        dock = theme.safe_container(key="coordinator-dock")
        with dock:
            edited = st.data_editor(
                display[display_cols],
                hide_index=True,
                use_container_width=True,
                height=420,
                key="coordinator_grid",
                disabled=["Column", "N tables", "Data product", "Assigned to", "Status"],
                column_config={"Description": st.column_config.TextColumn(width="large")},
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
                    orig_desc = filtered["description"].astype(str).to_numpy()
                    new_desc = edited["Description"].astype(str).to_numpy()
                    changed_mask = orig_desc != new_desc
                    if not changed_mask.any():
                        st.info("No description changes to save.")
                    else:
                        edits = [
                            {"column_name": n, "description": d, "_expected_updated_at": u}
                            for n, d, u in zip(
                                filtered.loc[changed_mask, "column_name"],
                                edited.loc[changed_mask, "Description"],
                                filtered.loc[changed_mask, "updated_at"],
                            )
                        ]
                        try:
                            workflow.save_rows(edits, actor=actor)
                            st.toast(f"Saved {len(edits)} description edit(s).", icon="✅")
                            st.rerun()
                        except workflow.WorkflowConflictError as exc:
                            st.error(f"{exc} Reload to see the latest version before retrying.")


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

        catalog_df = data.load_catalog()
        tables_by_col = {row["column_name"]: row["tables"] for _, row in catalog_df.iterrows()}

        for _, row in my_open.iterrows():
            col = row["column_name"]
            tables = tables_by_col.get(col, [])
            label = f"{col} — {row['data_product']} ({len(tables)} table{'s' if len(tables) != 1 else ''})"
            with st.expander(label):
                if tables:
                    st.caption("Appears in: " + ", ".join(tables))
                elif row["origin"] == "manual":
                    st.caption("Manual / glossary entry — no physical table.")

                draft_key = f"assignee_draft_{col}"
                st.session_state.setdefault(draft_key, row["description"])
                st.text_area("Description", key=draft_key, height=100, label_visibility="collapsed")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Save draft", key=f"save_draft_{col}", use_container_width=True):
                        try:
                            workflow.save_rows([{
                                "column_name": col,
                                "description": st.session_state[draft_key],
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
                                workflow.save_rows([{
                                    "column_name": col,
                                    "description": st.session_state[draft_key],
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

