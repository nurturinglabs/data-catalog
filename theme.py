"""
theme.py — CSS/branding + presentation helpers. Colors and titles are pulled
from config.py so a rebrand (a new PRIMARY_COLOR/ACCENT_COLOR/APP_TITLE)
requires no edits here. Reused by app.py; never imported by data.py.

Clickable "pills" (browse rail items, filter toggles) are native
`st.button`s whose chrome is stripped and restyled via CSS targeting
Streamlit's stable data-testid hooks (verified against the installed
frontend bundle: `stButton` wrapper, `stBaseButton-primary` /
`stBaseButton-secondary` on the button element itself). Each region is
wrapped in its own st.container() with an invisible marker element so the
*same* primary/secondary state can be styled differently per region (a rail
item looks different from a filter pill) via CSS `:has()` scoping. On a
Streamlit build old enough to lack `type=` on st.button, we degrade to a
plain button with a text marker instead of a hard crash.

The results list itself is a plain st.dataframe (row-click selection via
on_select), not buttons — no scoping needed there.
"""

from __future__ import annotations

import base64
import datetime as _dt
import html
import mimetypes
import os

import streamlit as st

import config

USAGE_ACCENT = "#1A6EB5"  # deliberately distinct from ACCENT_COLOR (gold),
# so the "Used by" list never visually blurs into the gold table reverse-index.

# The two top-level views, in menu order — the single source of truth for
# both header()'s inline nav menu and app.py's view -> render() dispatch,
# so the label list is never defined in more than one place.
NAV_ITEMS = ["Catalog", "Documentation workspace"]


# ─────────────────────────────────────────────────────────────────────────────
# Version-compat wrappers — local runs against whatever's pip-installed
# (currently 1.50.x); Streamlit-in-Snowflake pins its own, often older,
# runtime. Every call below wraps a Streamlit API whose signature grew a
# newer kwarg (or that didn't exist at all) somewhere in that gap, so a
# too-old SiS build degrades cosmetically instead of raising an uncaught
# TypeError/AttributeError mid-render. Approximate introduction versions,
# to the best of available knowledge (no changelog access from here):
#   st.button/st.form_submit_button `type=`     ~1.31
#   st.columns `gap=`                           ~1.31
#   st.columns `vertical_alignment=`             ~1.33
#   st.container `key=`/`border=`               ~1.34
#   st.dataframe `on_select=`/`selection_mode=`  ~1.35 (already guarded
#                                                 in views/catalog.py)
#   st.popover                                   ~1.27
#   st.multiselect `placeholder=`                ~1.35
#   st.progress `text=`                          ~1.29
# requirements.txt currently pins streamlit>=1.35, which covers all of the
# above — these wrappers are the fallback for whenever that pin and the
# actual deployed SiS runtime drift apart, which is exactly what happened
# to prompt this pass.
# ─────────────────────────────────────────────────────────────────────────────

def safe_container(key: str | None = None, **kwargs):
    """st.container(key=...) that degrades to a plain, unkeyed container
    (losing only its CSS hook — a cosmetic hit, not a crash) on a build too
    old for key=."""
    try:
        return st.container(key=key, **kwargs)
    except TypeError:
        return st.container()


def safe_columns(spec, **kwargs):
    """st.columns() that degrades gracefully on a build too old for one of
    the newer kwargs (gap, vertical_alignment, border) — retries with
    progressively fewer of them rather than crashing outright."""
    try:
        return st.columns(spec, **kwargs)
    except TypeError:
        for drop in ("vertical_alignment", "gap", "border"):
            if drop in kwargs:
                retry_kwargs = {k: v for k, v in kwargs.items() if k != drop}
                try:
                    return st.columns(spec, **retry_kwargs)
                except TypeError:
                    kwargs = retry_kwargs
                    continue
        return st.columns(spec)


def safe_popover(label: str):
    """st.popover if available, else st.expander as the closest native
    substitute (predates every Streamlit release this app could run on, so
    this branch always succeeds). Both return a context manager used the
    same way: `with theme.safe_popover(...):`."""
    if hasattr(st, "popover"):
        return st.popover(label)
    return st.expander(label)


def safe_multiselect(label: str, options, **kwargs):
    """st.multiselect that drops `placeholder=` if the installed build
    predates it, instead of raising."""
    try:
        return st.multiselect(label, options, **kwargs)
    except TypeError:
        kwargs.pop("placeholder", None)
        return st.multiselect(label, options, **kwargs)


def safe_progress(value: float, text: str | None = None) -> None:
    """st.progress that falls back to a plain caption under the bar if the
    installed build predates the text= kwarg."""
    try:
        st.progress(value, text=text)
    except TypeError:
        st.progress(value)
        if text:
            st.caption(text)


def action_button(label: str, key: str, primary: bool = False, **kwargs) -> bool:
    """A real action button (Assign, Approve, Add row, Submit — as opposed
    to toggle_button's toggle-state pills) with primary/secondary styling,
    degrading to a plain button on a build too old for `type=` (added
    1.31) instead of crashing the click."""
    try:
        return st.button(label, key=key, type=("primary" if primary else "secondary"), **kwargs)
    except TypeError:
        return st.button(label, key=key, **kwargs)


def action_form_submit_button(label: str, primary: bool = False, **kwargs) -> bool:
    """st.form_submit_button counterpart to action_button — same
    type=-unsupported fallback."""
    try:
        return st.form_submit_button(label, type=("primary" if primary else "secondary"), **kwargs)
    except TypeError:
        return st.form_submit_button(label, **kwargs)


def inject_css() -> None:
    primary = config.PRIMARY_COLOR
    accent = config.ACCENT_COLOR
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono&display=swap');
    html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
    .block-container {{
        padding-top: 1.5rem !important; padding-bottom: 4rem !important;
        max-width: 100% !important; padding-left: 2.25rem !important; padding-right: 2.25rem !important;
    }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}}
    div[data-testid="stVerticalBlock"] > div {{ gap: 0.5rem; }}
    code {{ font-family: 'DM Mono', monospace; }}

    /* Streamlit's own top header/toolbar — our navy header band replaces
       its visual chrome entirely. This app has no sidebar anywhere (page
       switching is the themed pill row below, not st.navigation/pages/),
       so — unlike an earlier version of this rule — there's no "expand
       sidebar" control that could ever need to live in this space; it's
       safe to collapse it outright. */
    header[data-testid="stHeader"] {{ background: transparent !important; height: 0 !important; min-height: 0 !important; overflow: hidden !important; }}

    /* Page nav (Catalog / Documentation workspace) now lives inline inside
       the navy header band itself — see .st-key-header-nav below,
       alongside the header's own styling — rather than as a standalone
       pill row above/below it. */

    /* ── Header band — a normal in-flow block at the top of the page (not
       position:fixed — that technique proved unreliable across several
       attempts in this environment for reasons I couldn't pin down without
       a browser to inspect, so it's not worth the risk here). Targeted via
       st.container(key="header-band"), which Streamlit turns directly into
       a stable .st-key-header-band class on the container's own element —
       no ancestor-matching :has() guesswork, which turned out to be
       unreliable specifically for this block despite working for the rail
       nav / tag pills / result cards elsewhere in this file. This needs to
       be a real Streamlit block, not a raw HTML div, because it holds a
       genuine interactive Refresh button in its top-right corner. ── */
    .st-key-header-band {{
        width: 100% !important; background: {primary} !important; box-shadow: none !important;
        border-bottom: 1px solid rgba(0,0,0,0.18);
        /* Symmetric vertical padding, not min-height + align-items, is what
           actually guarantees centering here: align-items:center on this
           element only centers its DIRECT child, and that child (an inner
           stVerticalBlock Streamlit inserts for every container) stretches
           to fill the full height rather than shrinking to its own content
           — so with a min-height the content sat at the top with dead
           space below, not centered. Equal top/bottom padding sidesteps
           that regardless of how many wrapper divs sit in between. */
        padding: 20px 20px !important; box-sizing: border-box;
        display: flex !important; align-items: center !important;
    }}
    .st-key-header-band div[data-testid="stHorizontalBlock"] {{
        display: flex !important; align-items: center !important; width: 100% !important;
    }}
    .header-brand {{ display: flex; align-items: center; gap: 10px; }}
    .header-icon {{ display: flex; align-items: center; color: {accent}; }}
    .header-icon svg {{ width: 20px; height: 20px; display: block; }}
    .header-logo {{ height: 28px; width: auto; max-width: 140px; object-fit: contain; }}
    .header-title {{ color: #fff; font-weight: 700; font-size: 19px; }}
    .header-tagline {{ color: #9DBBD9; font-size: 13.5px; margin-left: 4px; }}

    /* ── Page nav menu, inline in the header (Catalog / Documentation
       workspace) — flat text tabs, not buttons: no fill, no border, no
       shadow, no rounded box. Inactive is muted light-blue; active is
       white with only a 2px gold underline marking it.

       The underline is a border-bottom on the <button> element itself, so
       it is EXACTLY as wide as the button's own box — which is why the
       button must NOT be stretched (use_container_width=False, set in
       header() below) to fill an oversized, imprecisely-guessed column.
       An earlier version used True specifically so the button (and its
       trailing dead space) would visually reach the right edge — but that
       made the underline span the button's whole stretched box instead of
       just the text, which is exactly the "misaligned, too wide" underline
       this was rewritten to fix. With a content-sized button, the
       underline automatically tracks the label width, and the ~16px gap
       between the two tabs comes from st.columns()'s own native gap="small"
       (see header()) rather than from precise column-ratio math — a fixed,
       reliable value regardless of how good the character-count width
       guess turns out to be. ── */
    .st-key-header-nav div[data-testid="stButton"] {{
        /* flex-start (explicit, not just the default) so each
           content-sized button sits at the START of its own column —
           i.e. immediately after the previous tab (or the leading
           spacer) — rather than drifting toward that column's own far
           edge. This is what actually clusters the two tabs together:
           any leftover width from an imprecise column-size guess ends up
           as slack AFTER "Documentation workspace" (harmless), never
           BETWEEN the two tabs. */
        display: flex !important; align-items: center !important; justify-content: flex-start !important;
    }}
    .st-key-header-nav div[data-testid="stButton"] button {{
        background: transparent !important; border: none !important; box-shadow: none !important;
        border-radius: 0 !important; font-size: 14px !important; font-weight: 600 !important;
        padding: 4px 0 !important; margin: 0 !important; white-space: nowrap !important;
        border-bottom: 2px solid transparent !important;
        transition: color .12s, border-color .12s;
    }}
    .st-key-header-nav div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{
        color: #9DBBD9 !important;
    }}
    .st-key-header-nav div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {{
        color: #fff !important;
    }}
    .st-key-header-nav div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
        color: #fff !important; border-bottom: 2px solid {accent} !important;
    }}

    /* ── Tabs — styled to read as a continuation of the navy header: same
       background, flush against the header's bottom edge, no default
       Streamlit tab underline/border. Respects the page's normal side
       padding (not edge-to-edge) — kept simple deliberately after the
       edge-to-edge negative-margin version caused an unexplained rendering
       issue with no browser available to debug it further. ── */
    /* Pulls the tabs up to cancel the default gap Streamlit puts between
       stacked top-level blocks (the header container and this one), so
       they read as flush/attached rather than two separate bands. */
    .stTabs {{ margin-top: -1rem !important; }}
    .stTabs [data-baseweb="tab-list"] {{
        background: {primary} !important; gap: 4px; padding: 0 20px !important; margin: 0 !important;
        border-radius: 0 !important; border-bottom: none !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent !important; color: #93B8D8 !important; font-size: 13.5px !important;
        font-weight: 500 !important; padding: 14px 20px !important; border: none !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: {accent} !important; font-weight: 700 !important; border-bottom: 3px solid {accent} !important;
    }}
    .stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}
    .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}
    .stTabs [data-baseweb="tab-panel"] {{ padding-top: 20px !important; }}

    /* ── KPI stat tiles ──────────────────────────────────────────────── */
    .kpi-card {{
        background: #fff; border: 1px solid #E2E8F0; border-radius: 12px;
        padding: 18px 22px 20px; box-shadow: 0 1px 4px rgba(15,23,42,0.06);
        position: relative; overflow: hidden;
    }}
    /* Top accent bar (not a left bar) — reads as a stat-tile "header",
       distinct from the reverse-index/consumer list's left-border language
       used elsewhere, so the two visual idioms don't blur together. */
    .kpi-card::before {{
        content: ""; position: absolute; left: 0; top: 0; right: 0; height: 4px;
    }}
    .kpi-card.accent-primary::before {{ background: {primary}; }}
    .kpi-card.accent-yellow::before {{ background: {accent}; }}
    /* Single-color line icon (SVG, stroke=currentColor — see
       theme.ICON_COLUMNS/ICON_DESCRIPTION/ICON_LINK), not emoji; tinted to
       match its card's own accent color rather than a fixed neutral. */
    .kpi-icon {{ display: block; margin-bottom: 8px; line-height: 1; }}
    .kpi-icon svg {{ width: 18px; height: 18px; display: block; }}
    .kpi-card.accent-primary .kpi-icon {{ color: {primary}; }}
    .kpi-card.accent-yellow .kpi-icon {{ color: {accent}; }}
    .kpi-label {{ font-size: 11px; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 6px; font-weight: 600; }}
    /* Sans, not mono: a standalone hero-style number reads better in the
       font's default proportional figures — tabular/mono spacing is for
       columns of numbers that need to align vertically, not this. */
    .kpi-value {{
        font-size: 30px; font-weight: 700; color: {primary}; margin: 0; line-height: 1.15;
        font-family: 'DM Sans', sans-serif; word-break: break-word;
    }}

    /* ── Browse rail (sidebar) ───────────────────────────────────────── */
    .rail-label {{ font-size: 11px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; margin: 4px 0 8px; }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .rail-scope) div[data-testid="stButton"] button {{
        border: none !important; background: transparent !important; box-shadow: none !important;
        text-align: left !important; justify-content: flex-start !important; font-weight: 400 !important;
        padding: 7px 10px !important; border-radius: 6px !important; color: #334155 !important;
        white-space: pre-line !important; line-height: 1.4 !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .rail-scope) div[data-testid="stButton"] button:hover {{
        background: #F1F5F9 !important; color: {primary} !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .rail-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
        background: #E6F1FB !important; color: {primary} !important; font-weight: 600 !important;
    }}

    /* ── Tag pills (Catalog product/schema/table filters) — flat, matching
       the modernized header: no drop-shadow, no heavy border. Inactive is
       a thin hairline outline with muted text; active is a solid navy
       fill; a subtle background tint on hover, nothing raised/boxed. ── */
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button {{
        border-radius: 999px !important; padding: 0 18px !important; font-size: 12.5px !important;
        font-weight: 600 !important; height: 34px !important; min-height: 34px !important;
        min-width: 76px !important; white-space: nowrap !important; display: flex !important;
        align-items: center !important; justify-content: center !important; box-shadow: none !important;
        transition: background-color .12s, border-color .12s, color .12s;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] {{
        display: flex !important; align-items: flex-end !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{
        background: transparent !important; color: #64748B !important; border: 1px solid #D8DEE8 !important;
        box-shadow: none !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {{
        border-color: {primary} !important; background: #F8FAFC !important; color: {primary} !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
        background: {primary} !important; color: #fff !important; border: 1px solid {primary} !important;
        box-shadow: none !important;
    }}

    /* ── Role toggle (Documentation workspace: Coordinator / Assignee) ──
       Its own scope, not tags-scope: those pills get their width from a
       computed column ratio that can end up narrower than "Coordinator"
       needs (that's exactly what caused it to wrap to "Coor/dinat/or"
       after the control-line columns were tightened), so this one carries
       an explicit min-width instead of depending on column math, and
       redundant nowrap/word-break rules so a single long word is never
       broken even under a squeeze. Same segmented look as the tags-scope
       pills otherwise: 34px tall, rounded, navy-filled active / outlined
       inactive, small gap between them. ── */
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stButton"] button {{
        border-radius: 999px !important; padding: 0 20px !important; font-size: 13px !important;
        font-weight: 600 !important; height: 34px !important; min-height: 34px !important;
        min-width: 120px !important; white-space: nowrap !important; overflow-wrap: normal !important;
        word-break: keep-all !important; display: flex !important; align-items: center !important;
        justify-content: center !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stButton"] {{
        display: flex !important; align-items: flex-end !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stHorizontalBlock"] {{
        gap: 8px !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{
        background: #fff !important; color: {primary} !important; border: 1px solid #CBD5E1 !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {{
        border-color: {primary} !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .role-toggle-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
        background: {primary} !important; color: #fff !important; border: 1px solid {primary} !important;
    }}

    /* ── Tag pills used inside prose (detail panel) ──────────────────── */
    .pill {{
        display:inline-block; font-size:11px; font-weight:600; padding:3px 10px;
        border-radius:20px; margin: 0 6px 6px 0; letter-spacing: 0.01em;
    }}
    .pill-pii {{ background:#FCEBEB; color:#A32D2D; }}
    .pill-certified {{ background:#FFF3D6; color:#8A5A00; }}
    .pill-default {{ background:#E6F1FB; color:#0C447C; }}
    .pill-undocumented {{ background:#FAEEDA; color:#8A5A00; margin-left: 10px; vertical-align: middle; }}

    /* ── Detail panel ─────────────────────────────────────────────────── */
    .detail-card {{
        background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid {accent};
        border-radius: 10px; padding: 22px 24px; position: sticky; top: 20px;
    }}
    .detail-header {{ display: flex; align-items: center; flex-wrap: wrap; gap: 2px; }}
    .detail-name {{ font-size: 19px; font-weight: 700; color: {primary}; font-family: 'DM Mono', monospace; }}
    .detail-meta {{ font-size: 12px; color: #64748B; margin: 5px 0 14px; font-family: 'DM Mono', monospace; }}
    .detail-tags {{ margin-bottom: 4px; }}
    .detail-section-label {{ font-size: 10.5px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600; margin: 16px 0 6px; }}
    .detail-section-label:first-of-type {{ margin-top: 14px; }}
    .detail-text {{ font-size: 14px; color: #1E293B; margin: 0; line-height: 1.5; }}
    .detail-empty {{
        color: #8A5A00; background: #FFF8E8; border: 1px dashed #F0D48A; border-radius: 8px;
        padding: 10px 12px; font-size: 13px; font-style: italic;
    }}
    .detail-meta-strip {{ display: flex; gap: 22px; margin: 4px 0 4px; flex-wrap: wrap; }}
    .detail-meta-item .k {{ font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.06em; }}
    .detail-meta-item .v {{ font-size: 13px; color: #1E293B; font-weight: 500; }}
    .detail-tables {{ max-height: 240px; overflow-y: auto; }}
    .reverse-index-item {{
        border-left: 3px solid {accent}; padding: 6px 12px; margin-bottom: 5px;
        font-size: 12.5px; font-family: 'DM Mono', monospace; background: #fff;
        color: #334155; border-radius: 0 4px 4px 0;
    }}

    /* "Used by" (usage/consumers) — deliberately blue-accented, not gold,
       so it reads as a visually distinct list from the reverse-index. */
    .detail-consumers {{ max-height: 240px; overflow-y: auto; }}
    .consumer-item {{
        border-left: 3px solid {USAGE_ACCENT}; padding: 6px 12px; margin-bottom: 5px;
        background: #fff; border-radius: 0 4px 4px 0;
    }}
    .consumer-name-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .consumer-name {{ font-size: 12.5px; font-family: 'DM Mono', monospace; color: #334155; }}
    .consumer-meta {{ font-size: 10.5px; color: #94A3B8; margin-top: 2px; }}
    .usage-badge {{
        display: inline-block; font-size: 9.5px; font-weight: 600; padding: 1px 8px;
        border-radius: 20px; letter-spacing: 0.02em;
    }}
    .usage-badge-streamlit  {{ background: #FFE7E7; color: #B3261E; }}
    .usage-badge-dbt        {{ background: #FFE8DC; color: #B04A00; }}
    .usage-badge-dashboard  {{ background: #E6F1FB; color: #0C447C; }}
    .usage-badge-scheduled  {{ background: #EEEDFE; color: #3C3489; }}
    .usage-badge-adhoc      {{ background: #F1F5F9; color: #475569; }}
    .usage-badge-default    {{ background: #F1F5F9; color: #475569; }}

    /* ── Coverage strip (Documentation workspace) — a slim progress bar +
       inline stat pills replacing four large KPI cards; orientation, not
       the focus, so it stays compact. st.progress already renders navy
       for free (primaryColor in .streamlit/config.toml), no override
       needed. ── */
    .status-pill-row {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
    .status-pill {{
        display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
        font-weight: 600; padding: 6px 14px; border-radius: 999px; white-space: nowrap;
    }}
    .status-pill .n {{ font-size: 15px; font-weight: 800; }}
    .status-pill-unassigned {{ background: #F1F5F9; color: #475569; }}
    .status-pill-inprogress {{ background: #E6F1FB; color: #0C447C; }}
    .status-pill-submitted  {{ background: #FFF3D6; color: #8A5A00; }}
    .status-pill-approved   {{ background: #E6F7EC; color: #1E7A3D; }}

    /* ── Docked table (Documentation workspace coordinator grid) — the
       editor's own corners/border are flattened (the wrapping card
       supplies the outer rounding) and the default gap Streamlit puts
       between stacked blocks is zeroed out inside the dock. The action
       bar used to live inside this same card, flush against the grid's
       bottom edge; it's now position:fixed (see .st-key-coordinator-
       action-bar below) so it stays reachable regardless of table
       scroll — that necessarily detaches it from being physically flush
       against the grid's bottom border (a fixed element can't share a
       box with content that scrolls independently underneath it), so the
       dock card now just wraps the grid alone. ── */
    .st-key-coordinator-dock {{
        border: 1px solid #E2E8F0; border-radius: 10px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(15,23,42,0.06);
    }}
    .st-key-coordinator-dock div[data-testid="stVerticalBlock"] > div {{ gap: 0 !important; }}
    .st-key-coordinator-dock div[data-testid="stDataFrame"] {{
        border: none !important; border-radius: 0 !important;
    }}

    /* ── Sticky bulk-action bar — pinned to the bottom of the viewport
       (not the table) so Assign/Approve/Save stay reachable no matter how
       far the coordinator has scrolled down a long grid. left/right match
       .block-container's own 2.25rem side padding (this app has no
       sidebar to complicate that math) so its edges still line up with
       the table above it, even though it's no longer physically part of
       the same card. views/workspace.py adds a bottom spacer after the
       dock so this bar never overlaps the grid's last rows/controls.

       NOTE: position:fixed has been unreliable in this environment before
       (three earlier, never-fully-diagnosed failures trying to fix a
       sidebar toggle, a floating search box, and a fixed header — see
       git history) — but those all fought Streamlit's own native chrome
       (header/sidebar). This is a fixed element over plain page content,
       a much more commonly-solved case, so it's a reasonable attempt; it
       still needs real-browser confirmation, which isn't available here. ── */
    .st-key-coordinator-action-bar {{
        position: fixed !important; bottom: 0 !important; left: 2.25rem !important; right: 2.25rem !important;
        z-index: 999 !important; background: #F8FAFC !important; border-top: 1px solid #E2E8F0 !important;
        border-radius: 10px 10px 0 0 !important; box-shadow: 0 -2px 10px rgba(15,23,42,0.10) !important;
        padding: 14px 16px !important;
    }}

    /* Misc widget polish */
    div[data-testid="stCheckbox"] label p {{ font-size: 13.5px !important; }}
    div[data-testid="stDataFrame"] {{ border-radius: 8px; overflow: hidden; }}
    </style>
    """, unsafe_allow_html=True)


_BOOK_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0 -3 -3H2z"></path>'
    '<path d="M22 3h-6a4 4 0 0 0 -4 4v14a3 3 0 0 1 3 -3h7z"></path>'
    '</svg>'
)

# KPI card icons — same single-color line-icon convention as the header's
# book icon (24x24 viewBox, 2px stroke, rounded caps/joins), not emoji.
# Exported (not "_"-prefixed) since views/catalog.py passes these directly
# as kpi_row()'s "icon" values.
ICON_COLUMNS = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="18" y1="20" x2="18" y2="10"></line>'
    '<line x1="12" y1="20" x2="12" y2="4"></line>'
    '<line x1="6" y1="20" x2="6" y2="14"></line>'
    '</svg>'
)

ICON_DESCRIPTION = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>'
    '<polyline points="14 2 14 8 20 8"></polyline>'
    '<line x1="16" y1="13" x2="8" y2="13"></line>'
    '<line x1="16" y1="17" x2="8" y2="17"></line>'
    '</svg>'
)

ICON_LINK = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>'
    '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>'
    '</svg>'
)


def _logo_html() -> str:
    """Render config.HEADER_LOGO_PATH as an inline base64 <img>, so it works
    identically locally and in Streamlit-in-Snowflake (no static file
    serving required). Falls back to a single-color inline SVG line icon
    (a book, matching Tabler Icons' stroke conventions — 24x24 viewBox, 2px
    stroke, rounded joins) when unset/unreadable — deliberately not an
    emoji, which renders as an inconsistent cartoon sticker across
    platforms/fonts."""
    logo_path = getattr(config, "HEADER_LOGO_PATH", "")
    if logo_path and os.path.isfile(logo_path):
        mime, _ = mimetypes.guess_type(logo_path)
        mime = mime or "image/png"
        with open(logo_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f'<img class="header-logo" src="data:{mime};base64,{encoded}" alt="logo">'
    return f'<span class="header-icon">{_BOOK_ICON_SVG}</span>'


def header(nav_items: list[str] | None = None) -> None:
    """Render the slim navy header: a line-icon wordmark on the left, an
    optional inline nav menu on the right (Catalog / Documentation
    workspace, e.g.) styled as flat text tabs — no fill, no border, no
    shadow; the active one gets a 2px gold underline, nothing else.

    When nav_items is given, clicking one updates
    st.session_state["active_view"] and reruns immediately — the caller
    (app.py's router) picks up the new value on its next run without
    needing to handle the click itself. This is why the same two labels
    get passed from both views/catalog.py and views/workspace.py: whichever
    view happens to be showing renders the *same* menu, just reflecting
    whichever one is currently active.

    key="header-band" (and, for the nav sub-region, key="header-nav") is
    what makes this stylable: Streamlit turns a container's key= directly
    into a stable `.st-key-<name>` class on that container's own DOM
    element (verified against the installed frontend bundle), which CSS
    targets directly — no ancestor :has() matching needed, which turned out
    to be unreliable for this specific block."""
    container = safe_container(key="header-band")
    with container:
        left, nav_col = st.columns([2.4, 5.6])
        with left:
            st.markdown(f"""
            <div class="header-brand">
              {_logo_html()}
              <span class="header-title">{html.escape(config.APP_TITLE)}</span>
              <span class="header-tagline">· {html.escape(config.APP_SUBTITLE)}</span>
            </div>
            """, unsafe_allow_html=True)
        if nav_items:
            with nav_col:
                active = st.session_state.get("active_view", nav_items[0])
                nav_container = safe_container(key="header-nav")
                with nav_container:
                    # A leading spacer pushes the pair to the right side of
                    # nav_col. use_container_width=False (not True) is the
                    # key fix here: each button stays exactly as wide as
                    # its own label, so its border-bottom underline (the
                    # active-state indicator) hugs the text instead of
                    # spanning a stretched, guessed-width column. gap=
                    # "small" gives the two tabs a fixed, reliable ~16px
                    # separation regardless of that guess's precision —
                    # native column spacing, not CSS margin math.
                    widths = [len(v) + 2 for v in nav_items]
                    cols = safe_columns([max(sum(widths), 1)] + widths, gap="small")
                    for col, label in zip(cols[1:], nav_items):
                        with col:
                            if toggle_button(
                                label, key=f"header_nav_{label}",
                                active=(active == label), use_container_width=False,
                            ):
                                st.session_state["active_view"] = label
                                st.rerun()




def kpi_row(metrics: list[dict]) -> None:
    """Each metric dict: {"label": str, "value": str, "icon": str (optional,
    trusted inline SVG markup — e.g. theme.ICON_COLUMNS — not emoji or
    user-supplied text; rendered unescaped), "accent": "primary"|"yellow"
    (optional — defaults to alternating by position if omitted)}."""
    cols = st.columns(len(metrics))
    for i, (col, m) in enumerate(zip(cols, metrics)):
        accent = m.get("accent") or ("primary" if i % 2 == 0 else "yellow")
        accent_cls = f"accent-{accent}"
        icon_html = f'<span class="kpi-icon">{m["icon"]}</span>' if m.get("icon") else ""
        with col:
            st.markdown(f"""
            <div class="kpi-card {accent_cls}">
              {icon_html}
              <p class="kpi-label">{html.escape(m['label'])}</p>
              <p class="kpi-value">{html.escape(str(m['value']))}</p>
            </div>
            """, unsafe_allow_html=True)


_STATUS_PILL_CLASSES = {
    "unassigned": "status-pill-unassigned",
    "in progress": "status-pill-inprogress",
    "submitted": "status-pill-submitted",
    "approved": "status-pill-approved",
}


def coverage_strip(coverage_pct: float, counts: dict[str, int]) -> None:
    """A slim orientation strip — a native progress bar (already navy via
    .streamlit/config.toml's primaryColor, no CSS override needed) plus
    inline colored stat pills, one per status count. Replaces four large
    KPI cards: this is orientation, not the focus, so it stays compact.
    counts should be an ordered dict/mapping of status label -> count."""
    prog_col, pills_col = safe_columns([2, 4], vertical_alignment="center")
    with prog_col:
        safe_progress(min(max(coverage_pct / 100, 0.0), 1.0), text=f"{coverage_pct:.0f}% approved")
    with pills_col:
        pills_html = "".join(
            f'<span class="status-pill {_STATUS_PILL_CLASSES.get(label.lower(), "status-pill-unassigned")}">'
            f'<span class="n">{count}</span> {html.escape(label)}</span>'
            for label, count in counts.items()
        )
        st.markdown(f'<div class="status-pill-row">{pills_html}</div>', unsafe_allow_html=True)


def tag_pill(tag: str) -> str:
    key = tag.strip().lower()
    style = {"pii": "pill-pii", "certified": "pill-certified"}.get(key, "pill-default")
    icon = {"pii": "🔒 ", "certified": "✓ "}.get(key, "")
    return f'<span class="pill {style}">{icon}{html.escape(tag)}</span>'


def undocumented_badge() -> str:
    return '<span class="pill pill-undocumented">Undocumented</span>'


_USAGE_BADGE_CLASSES = {
    "streamlit app": "usage-badge-streamlit",
    "dbt model": "usage-badge-dbt",
    "dashboard": "usage-badge-dashboard",
    "scheduled query": "usage-badge-scheduled",
    "user / ad-hoc": "usage-badge-adhoc",
}


def _consumer_type_badge(consumer_type: str) -> str:
    cls = _USAGE_BADGE_CLASSES.get(consumer_type.strip().lower(), "usage-badge-default")
    return f'<span class="usage-badge {cls}">{html.escape(consumer_type)}</span>'


def _relative_time(date_str) -> str:
    """'3 days ago' / 'today' / '2 months ago' style relative label for an
    ISO-ish date string. Falls back to the raw string if unparseable."""
    if not date_str:
        return ""
    try:
        parsed = _dt.date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return str(date_str)
    days = (_dt.date.today() - parsed).days
    if days < 0:
        return str(date_str)
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = max(1, days // 30)
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(1, days // 365)
    return f"{years} year{'s' if years != 1 else ''} ago"


def _render_consumer_item(consumer: dict) -> str:
    name = html.escape(str(consumer.get("name", "")))
    ctype = str(consumer.get("type", ""))
    badge = _consumer_type_badge(ctype)

    meta_parts = []
    last_used = consumer.get("last_used")
    if last_used:
        meta_parts.append(f"last read {_relative_time(last_used)}")
    query_count = consumer.get("query_count")
    if query_count is not None:
        meta_parts.append(f"{query_count:,} queries")
    meta_html = f'<div class="consumer-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""

    return (
        '<div class="consumer-item">'
        f'<div class="consumer-name-row"><span class="consumer-name">{name}</span>{badge}</div>'
        f'{meta_html}'
        '</div>'
    )


def scope_marker(name: str) -> None:
    """Invisible marker so a following region's buttons can be styled
    distinctly via a `:has()` CSS scope (see inject_css)."""
    st.markdown(f'<span class="{name}" style="display:none"></span>', unsafe_allow_html=True)


def toggle_button(label: str, key: str, active: bool, use_container_width: bool = True) -> bool:
    """A button whose primary/secondary state is used purely as a CSS hook
    for "active" styling. Degrades to a plain button with a text marker on
    Streamlit builds old enough to lack the `type=` kwarg (added 1.31)."""
    try:
        return st.button(
            label, key=key, type=("primary" if active else "secondary"),
            use_container_width=use_container_width,
        )
    except TypeError:
        marker = "● " if active else "○ "
        return st.button(marker + label, key=key, use_container_width=use_container_width)


def pill_row(
    marker_key: str, values: list[str], selected: str, on_pick,
    scope: str = "tags-scope", max_per_row: int = 6,
) -> None:
    """A single-select row of toggle_button pills, each column sized to its
    own label's length so nothing truncates (short filter values and long
    page names alike). Clicking a pill calls on_pick(value) and reruns.
    scope picks which CSS region this row styles as — "tags-scope" for
    in-page filter pills — the top-level Catalog/Documentation workspace
    switcher lives inline in header() instead, not as a pill_row (see
    inject_css's .st-key-header-nav).

    Values are chunked into rows of at most max_per_row: st.columns()
    never wraps a single row on its own, so a long value list (e.g. a
    product with many schemas) would otherwise cram every pill onto one
    ever-narrower line — which is also why an "All ..." pill's size used
    to vary from product to product, purely as a side effect of how many
    *other* pills happened to share its row that time. Each row's pills
    stretch to fill the full width (no trailing spacer siphoning off
    space that could go to the pills), and a CSS min-width (see
    inject_css's .tags-scope rule) is the hard floor that keeps a label
    from being squeezed illegibly small when a row is nearly full."""
    with st.container():
        scope_marker(scope)
        for start in range(0, len(values), max_per_row):
            chunk = values[start:start + max_per_row]
            widths = [len(v) + 4 for v in chunk]
            cols = st.columns(widths)
            for col, value in zip(cols, chunk):
                with col:
                    if toggle_button(value, key=f"{marker_key}_{value}", active=(selected == value)):
                        on_pick(value)
                        st.rerun()


def render_detail_card(row, usage_status: str | None = None) -> None:
    """Render the entire column-detail pane as one cohesive HTML block.

    usage_status comes from data.load_health()["usage_status"] ("ok",
    "empty", "disabled", or an "unavailable: ..." reason). When
    config.USAGE_ENABLED is False the "Used by" section is omitted
    entirely; otherwise a non-"ok" status swaps the per-column consumer
    list for a single "not available" line instead of erroring.
    """
    name = html.escape(str(row["column_name"]))
    data_type = html.escape(str(row["data_type"])) or "—"
    documented = bool(row["documented"])
    badge_html = "" if documented else undocumented_badge()

    schemas = row["schemas"]
    scope_label = ", ".join(schemas[:2]) + (f" +{len(schemas) - 2} more" if len(schemas) > 2 else "")

    tags_html = ""
    if row["tags"]:
        tags_html = f'<div class="detail-tags">{"".join(tag_pill(t) for t in row["tags"])}</div>'

    if row["description"]:
        description_html = f'<p class="detail-text">{html.escape(row["description"])}</p>'
    else:
        description_html = '<div class="detail-empty">This column doesn\'t have a description yet.</div>'

    steward = html.escape(row["steward"]) if row["steward"] else "—"
    approved_label = "✓ Approved" if row["approved"] else "Not approved"

    tables = row["tables"]
    n_tables = len(tables)
    table_word = "table" if n_tables == 1 else "tables"
    tables_html = "".join(
        f'<div class="reverse-index-item">{html.escape(t)}</div>' for t in tables
    )

    usage_html = ""
    if config.USAGE_ENABLED:
        consumers = row["consumers"] or []
        if usage_status not in (None, "ok"):
            consumers_body = '<div class="detail-meta">Usage data not available in this environment.</div>'
        elif consumers:
            consumers_body = (
                '<div class="detail-consumers">'
                + "".join(_render_consumer_item(c) for c in consumers)
                + "</div>"
            )
        else:
            consumers_body = '<div class="detail-meta">No recorded consumers.</div>'
        count_suffix = f" ({len(consumers)})" if consumers else ""
        usage_html = f"""
      <p class="detail-section-label">Used by{count_suffix}</p>
      {consumers_body}"""

    st.markdown(f"""
    <div class="detail-card">
      <div class="detail-header">
        <span class="detail-name">{name}</span>{badge_html}
      </div>
      <div class="detail-meta">{data_type} · {html.escape(scope_label)}</div>
      {tags_html}
      <p class="detail-section-label">Description</p>
      {description_html}
      <div class="detail-meta-strip">
        <div class="detail-meta-item"><div class="k">Steward</div><div class="v">{steward}</div></div>
        <div class="detail-meta-item"><div class="k">Approval</div><div class="v">{approved_label}</div></div>
      </div>
      <p class="detail-section-label">Used in {n_tables} {table_word} — live from schema</p>
      <div class="detail-tables">{tables_html}</div>
      {usage_html}
    </div>
    """, unsafe_allow_html=True)
