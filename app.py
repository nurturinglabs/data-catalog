"""
app.py — the app's entrypoint/router. Declares page config and shared CSS
once (they must run exactly once per session regardless of which view is
showing), then dispatches to whichever of the two views/ (Catalog, the read
side; Documentation workspace, the write side) is currently active.

The nav menu that switches between them is NOT rendered here — it's inline
inside the navy header band itself (see theme.header(nav_items=...)),
called from within each view's own render(). Clicking a menu item updates
st.session_state["active_view"] and reruns; this file just reads that value
on the next run and calls the matching render().

Deliberately NOT using st.navigation/st.Page: this app has no sidebar
anywhere else, and Streamlit's built-in page nav (sidebar position, or the
newer top position) renders through native chrome we cannot restyle or
verify without a browser — the sidebar variant is what truncated page
labels and, in an earlier version of this app, briefly made the nav
unreachable when collapsed (its only "expand" control lives inside the
native header). The header-menu approach reuses the exact same
toggle_button pattern already proven throughout this app (the
product/schema/table filters), so its behavior and styling are fully within
our control.

The directory holding the two views is deliberately named views/, not
pages/ — "pages" is a magic directory name to Streamlit's own legacy
multipage auto-discovery, which would reinstate its default sidebar nav the
moment the folder exists, regardless of anything done here.
"""

import streamlit as st

import config
import theme
from views import catalog, workspace

st.set_page_config(
    page_title=f"{config.APP_TITLE}",
    page_icon="📚",
    layout="wide",
)

theme.inject_css()

VIEWS = dict(zip(theme.NAV_ITEMS, [catalog.render, workspace.render]))

st.session_state.setdefault("active_view", theme.NAV_ITEMS[0])

VIEWS[st.session_state["active_view"]]()
