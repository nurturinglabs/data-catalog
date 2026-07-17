# Data Catalog

A searchable, browsable column catalog that joins a **curated description
layer** (Excel) to a **live structure layer** (Snowflake schema), so
descriptions are authored once and structure is always current.

## Architecture

A catalog entry = one curated meaning joined to live structural facts.

- **Layer 1 — Descriptions (curated).** Human-authored `description`, `tags`,
  `steward`, keyed on column name. Source of truth: Excel (local file, staged
  file, or a Snowflake table loaded from Excel).
- **Layer 2 — Structure (harvested).** Read live: `data_type` and the
  **reverse index** — every `DATABASE.SCHEMA.TABLE` the column appears in.
  Source of truth: `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS` (org-wide) or a single
  database's `INFORMATION_SCHEMA.COLUMNS` (zero latency).

The two layers are joined on column name. Descriptions never go stale;
structure never needs maintenance.

## Run locally

```bash
pip install -r requirements.txt
python sample_data/_generate.py   # regenerate the demo sources (optional; already committed)
pytest                             # data-layer tests
streamlit run app.py
```

The demo ships with `sample_data/structure.csv` (75 physical columns across 3
databases / 5 schemas / 13 tables) and `sample_data/descriptions.xlsx`
(partial coverage, ~70%), so the reverse index and the undocumented filter
both have real content out of the box.

## The config-only port

Moving from this local demo to production Streamlit-in-Snowflake requires
editing **`config.py` only** — never `app.py` or `data.py`. A reviewer
diffing a demo branch against a production branch should see changes
confined to `config.py`.

### Step 1 — point Layer 1 at the real Excel

Pick one:

- `DESCRIPTIONS_SOURCE = "excel_local"` — a file on disk (only works when
  running locally, not in SiS).
- `DESCRIPTIONS_SOURCE = "excel_stage"` — reads via
  `session.file.get(...)` + `pd.read_excel`. Works in SiS but this path
  **varies across SiS Streamlit runtime versions** — test it in your target
  environment before relying on it.
- `DESCRIPTIONS_SOURCE = "snowflake_table"` — **the recommended production
  route.** Load the curated Excel into a table once (e.g. via a scheduled
  task or a one-time `COPY INTO`), then point `DESC_SNOWFLAKE_TABLE` at it.
  This is the most robust option in SiS and avoids the stage-read version
  sensitivity entirely.

Update `DESCRIPTION_MAP` if your header names differ from `Column Name` /
`Description` / `Tags` / `Steward`.

### Step 2 — point Layer 2 at the live schema

Set `STRUCTURE_SOURCE = "information_schema"`. This runs `STRUCTURE_QUERY`
against `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS`, which requires:

- **`IMPORTED PRIVILEGES` on the `SNOWFLAKE` database**, granted to the role
  the SiS app runs as.
- Tolerance for **up to ~90 minutes of latency** — `ACCOUNT_USAGE` views are
  not real-time. If you need zero-latency structure for a single database,
  swap `STRUCTURE_QUERY` to select from that database's own
  `INFORMATION_SCHEMA.COLUMNS` instead — same shape, no grant needed, no
  latency, but scoped to one database only.

Use `DATABASE_ALLOWLIST` to restrict the pull to specific databases (also
narrows `MAX_STRUCTURE_ROWS` exposure).

That's it — no other files change. `data.py` obtains the Snowflake session
via `get_active_session()` lazily inside each reader; it is never imported
at module load time, so the app still runs locally with no Snowflake
libraries installed.

## Repository structure

```
app.py                    # UI. Depends only on data.load_catalog() + config.
data.py                   # Two-layer load + join + validation. The seam.
config.py                 # ALL source/mapping/branding knobs. Only file edited to port.
theme.py                  # CSS/colors pulled from config, reused by app.
requirements.txt
sample_data/
  _generate.py            # Regenerates the two synthetic sources.
  structure.csv           # INFORMATION_SCHEMA-shaped demo structure.
  descriptions.xlsx        # Curated demo descriptions (partial coverage).
tests/
  test_data.py            # Data-layer unit tests, no Snowflake required.
```

## Production-readiness features

- **Pagination** — results never render more than one page; page size ∈
  {25, 50, 100}.
- **Source & mapping validation** — a missing required header raises a
  specific `ValueError` naming the source, field, and expected/actual
  headers; a missing optional header just gets recorded in health and
  defaults empty. Unreachable sources surface as a clean `st.error`, not a
  stack trace.
- **Query scoping** — `DATABASE_ALLOWLIST` restricts structure across every
  source type (SQL predicate for `information_schema`, pandas filter for
  csv/table sources).
- **Catalog health panel** — an expander showing source types, row counts,
  headers found/missing, coverage, join grain, and any truncation.
- **Click-to-select rows** — uses `st.dataframe(on_select=...)` where
  available, with an automatic selectbox fallback and no hard dependency on
  a specific Streamlit version.
- **CSV export** — downloads the current filtered view with list columns
  flattened to comma-separated strings.
- **Caching with TTL** — `st.cache_data(ttl=CACHE_TTL_SECONDS)`; a Refresh
  button in the sidebar clears the cache and reloads.

## Non-goals (v1)

- Column-level lineage ("feeds into / derived from"). The detail pane is
  structured so a second "Lineage" tab can be added later (e.g. fed from a
  dbt `manifest.json` reader) without touching the description/structure
  layers.
- Write-back / editing of descriptions from the UI — Excel (or the table
  it's loaded into) stays the authoring surface.
- No auth/roles beyond what Streamlit-in-Snowflake enforces natively.
