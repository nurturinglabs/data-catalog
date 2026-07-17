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

import base64
import html
import mimetypes
import os

import streamlit as st

import config


def inject_css() -> None:
    primary = config.PRIMARY_COLOR
    accent = config.ACCENT_COLOR
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono&display=swap');
    html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
    .block-container {{ padding-top: 0.6rem !important; padding-bottom: 4rem !important; max-width: 1500px; }}
    #MainMenu {{visibility: hidden;}} footer {{visibility: hidden;}}
    div[data-testid="stVerticalBlock"] > div {{ gap: 0.5rem; }}
    code {{ font-family: 'DM Mono', monospace; }}

    /* Hide Streamlit's own top toolbar — our fixed header replaces it */
    header[data-testid="stHeader"], div[data-testid="stAppHeader"] {{ display: none !important; }}

    /* ── Header band — fixed, full viewport width, above sidebar + content ── */
    .catalog-header {{
        position: fixed; top: 0; left: 0; right: 0; width: 100%; height: 72px;
        z-index: 999998; background: {primary}; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        display: flex; align-items: center; justify-content: space-between;
        padding: 0 26px; box-sizing: border-box;
    }}
    .catalog-header .brand {{ display: flex; align-items: center; gap: 12px; }}
    .catalog-header .icon {{ font-size: 22px; }}
    .catalog-header .header-logo {{ height: 32px; width: auto; max-width: 140px; object-fit: contain; }}
    .catalog-header .title {{ color: {accent}; font-weight: 700; font-size: 19px; letter-spacing: -0.02em; }}
    .catalog-header .subtitle {{ color: #C7D9EE; font-size: 12px; margin-top: 1px; }}

    /* Push page content below the fixed header. Applied to stMain — the
       actual scrolling element (height:100dvh; overflow:auto) — not to the
       outer stAppViewContainer, which is position:absolute + overflow:hidden
       and doesn't scroll at all. Padding the wrong one pushes content past
       the bottom of a fixed-size box with no way to scroll to reach it. */
    section[data-testid="stMain"] {{ padding-top: 72px !important; }}

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
        border-radius: 10px; padding: 22px 24px; position: sticky; top: 76px;
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
    return f'<span class="icon">{html.escape(icon)}</span>'


def header() -> None:
    st.markdown(f"""
    <div class="catalog-header">
      <div class="brand">
        {_logo_html()}
        <div>
          <div class="title">{html.escape(config.APP_TITLE)}</div>
          <div class="subtitle">{html.escape(config.APP_SUBTITLE)}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)




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


def render_detail_card(row) -> None:
    """Render the entire column-detail pane as one cohesive HTML block."""
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

    tables = row["tables"]
    n_tables = len(tables)
    table_word = "table" if n_tables == 1 else "tables"
    tables_html = "".join(
        f'<div class="reverse-index-item">{html.escape(t)}</div>' for t in tables
    )

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
      </div>
      <p class="detail-section-label">Used in {n_tables} {table_word} — live from schema</p>
      <div class="detail-tables">{tables_html}</div>
    </div>
    """, unsafe_allow_html=True)
