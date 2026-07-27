"""
app.py — the app's entrypoint/router. Declares the two pages (Catalog, the
read side; Documentation workspace, the write side) and hands off to
whichever is active via st.navigation. Page config and shared CSS are set
once here, since they must run exactly once per session regardless of which
page is showing — the page bodies themselves live under pages/.
"""

import streamlit as st

import config
import theme

st.set_page_config(
    page_title=f"{config.APP_TITLE}",
    page_icon="📚",
    layout="wide",
)

theme.inject_css()

pg = st.navigation([
    st.Page("pages/catalog.py", title="Catalog", icon="📚", default=True),
    st.Page("pages/workspace.py", title="Documentation workspace", icon="📝"),
])
pg.run()
