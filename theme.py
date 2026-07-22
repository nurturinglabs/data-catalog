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


def inject_css() -> None:
    primary = config.PRIMARY_COLOR
    accent = config.ACCENT_COLOR
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono&display=swap');
    html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
    .block-container {{
        padding-top: 0 !important; padding-bottom: 4rem !important;
        max-width: 100% !important; padding-left: 2.25rem !important; padding-right: 2.25rem !important;
    }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}}
    div[data-testid="stVerticalBlock"] > div {{ gap: 0.5rem; }}
    code {{ font-family: 'DM Mono', monospace; }}

    /* Hide Streamlit's own top toolbar — our header replaces it */
    header[data-testid="stHeader"], div[data-testid="stAppHeader"] {{ display: none !important; }}
    section[data-testid="stMain"] {{ padding-top: 0 !important; }}

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
        width: 100% !important; background: {primary} !important; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        padding: 20px 36px !important; box-sizing: border-box; display: flex !important; align-items: center !important;
    }}
    .st-key-header-band div[data-testid="stHorizontalBlock"] {{
        display: flex !important; align-items: center !important; width: 100% !important;
    }}
    .header-brand {{ display: flex; align-items: center; gap: 14px; }}
    .header-icon {{ font-size: 26px; }}
    .header-logo {{ height: 42px; width: auto; max-width: 160px; object-fit: contain; }}
    .header-divider {{ width: 2px; height: 38px; background: {accent}; display: inline-block; }}
    .header-title {{ color: {accent}; font-weight: 700; font-size: 23px; letter-spacing: -0.02em; }}
    .header-subtitle {{ color: #CFE3E1; font-size: 13px; margin-top: 3px; }}

    /* Refresh button living inside the header, right side — a solid gold
       pill, matching the same pill language as the tag filters, so it pops
       against the navy header instead of blending in as an outline. */
    .st-key-header-band div[data-testid="stButton"] button {{
        background: {accent} !important; border: none !important;
        color: {primary} !important; border-radius: 999px !important; font-size: 12.5px !important;
        font-weight: 700 !important; padding: 8px 18px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2) !important; transition: filter .12s, box-shadow .12s;
    }}
    .st-key-header-band div[data-testid="stButton"] button:hover {{
        filter: brightness(1.08); box-shadow: 0 2px 6px rgba(0,0,0,0.3) !important;
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
        background: #fff; border: 1px solid #E2E8F0; border-radius: 10px;
        padding: 16px 20px; box-shadow: 0 1px 3px rgba(15,23,42,0.05);
        position: relative; overflow: hidden;
    }}
    .kpi-card::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }}
    .kpi-card.accent-primary::before {{ background: {primary}; }}
    .kpi-card.accent-yellow::before {{ background: {accent}; }}
    .kpi-label {{ font-size: 11px; color: #64748B; text-transform: uppercase; letter-spacing: 0.06em; margin: 0 0 8px; font-weight: 500; }}
    .kpi-value {{
        font-size: 24px; font-weight: 700; color: {primary}; margin: 0; line-height: 1.2;
        font-family: 'DM Mono', monospace; word-break: break-word;
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

    /* ── Tag pills ────────────────────────────────────────────────────── */
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button {{
        border-radius: 999px !important; padding: 0 16px !important; font-size: 12.5px !important;
        font-weight: 600 !important; height: 34px !important; min-height: 34px !important;
        white-space: nowrap !important; display: flex !important; align-items: center !important;
        justify-content: center !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] {{
        display: flex !important; align-items: flex-end !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"] {{
        background: #fff !important; color: {primary} !important; border: 1px solid #CBD5E1 !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-secondary"]:hover {{
        border-color: {primary} !important;
    }}
    div[data-testid="stVerticalBlock"]:has(> div[data-testid="element-container"] .tags-scope) div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] {{
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

    /* Misc widget polish */
    div[data-testid="stCheckbox"] label p {{ font-size: 13.5px !important; }}
    div[data-testid="stDataFrame"] {{ border-radius: 8px; overflow: hidden; }}
    </style>
    """, unsafe_allow_html=True)


def _logo_html() -> str:
    """Render config.HEADER_LOGO_PATH as an inline base64 <img>, so it works
    identically locally and in Streamlit-in-Snowflake (no static file
    serving required). Falls back to HEADER_ICON if unset/unreadable."""
    logo_path = getattr(config, "HEADER_LOGO_PATH", "")
    if logo_path and os.path.isfile(logo_path):
        mime, _ = mimetypes.guess_type(logo_path)
        mime = mime or "image/png"
        with open(logo_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f'<img class="header-logo" src="data:{mime};base64,{encoded}" alt="logo">'
    icon = getattr(config, "HEADER_ICON", "📚")
    return f'<span class="header-icon">{html.escape(icon)}</span>'


def header():
    """Render the navy header (logo/title/tagline on the left) and return a
    Streamlit column for the right side, so the caller can place a real
    interactive widget there (e.g. a Refresh button) that visually sits in
    the header's top-right corner. The whole thing — markdown title block
    and the caller's widget alike — lives in one Streamlit block, so
    there's no separate floating-element alignment to fight with.

    key="header-band" is what makes this stylable: Streamlit turns a
    container's key= directly into a `.st-key-header-band` class on that
    container's own DOM element (verified against the installed frontend
    bundle), which CSS targets directly — no ancestor :has() matching
    needed, which turned out to be unreliable for this specific block."""
    container = st.container(key="header-band")
    with container:
        left, right = st.columns([6, 1])
        with left:
            st.markdown(f"""
            <div class="header-brand">
              {_logo_html()}
              <span class="header-divider"></span>
              <div>
                <div class="header-title">{html.escape(config.APP_TITLE)}</div>
                <div class="header-subtitle">{html.escape(config.APP_SUBTITLE)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)
    return right




def kpi_row(metrics: list[dict]) -> None:
    cols = st.columns(len(metrics))
    for i, (col, m) in enumerate(zip(cols, metrics)):
        accent_cls = "accent-primary" if i % 2 == 0 else "accent-yellow"
        with col:
            st.markdown(f"""
            <div class="kpi-card {accent_cls}">
              <p class="kpi-label">{html.escape(m['label'])}</p>
              <p class="kpi-value">{html.escape(str(m['value']))}</p>
            </div>
            """, unsafe_allow_html=True)


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
