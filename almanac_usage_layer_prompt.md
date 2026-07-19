# Claude Code prompt — add a "who uses this column" layer (Usage / Consumers)

Add a third data layer to the `nurturinglabs/data-catalog` (Almanac) repo:
**usage** — for each column, who actually reads it (Streamlit apps, dbt models,
dashboards, scheduled queries, users). This joins onto the existing catalog the
same way the description and structure layers do.

## Non-negotiable constraint — no Snowflake yet
There is NO Snowflake connection available right now. This must run entirely on
**synthetic local data** today, and switch to real Snowflake `ACCESS_HISTORY`
later with a **config change only** — exactly mirroring how `STRUCTURE_SOURCE`
already toggles between `local_csv` and `information_schema`. Default the new
source to the local synthetic file. Do not require Snowflake to run or test.

## Keep intact
- The config-only-port principle and the two existing layers (descriptions,
  structure) unchanged.
- The one allowed change to the canonical contract is **additive** (see below) —
  add a field, break nothing existing.

## config.py — add a usage layer block
- `USAGE_SOURCE`: `"local_csv" | "access_history" | "snapshot_table"`
  (default `"local_csv"`).
- `USAGE_LOCAL_CSV = {"path": "sample_data/usage.csv"}`
- `USAGE_SNAPSHOT_TABLE = {"table": "CATALOG_DB.GOVERNANCE.USAGE_SNAPSHOT"}`
- `USAGE_QUERY`: the `ACCESS_HISTORY`-based SQL used when
  `USAGE_SOURCE == "access_history"` (template provided at the bottom of this
  prompt — paste it as the default value).
- `USAGE_MAP`: map source headers → canonical usage fields:
  `column_name` (req), `table` (opt), `consumer_name` (req),
  `consumer_type` (req), `last_used` (opt), `query_count` (opt).
- `USAGE_ENABLED = True` — a master switch; when False the app hides all usage
  UI and skips the usage load entirely (so it can be turned off cleanly).

## data.py — load, normalize, aggregate, join
- Add a usage reader alongside the existing ones:
  - `local_csv` → `pd.read_csv`.
  - `access_history` → `get_active_session().sql(USAGE_QUERY).to_pandas()`
    (lazy Snowpark import, same pattern as the structure reader).
  - `snapshot_table` → read the table via the session.
- Normalize through `USAGE_MAP` into rows of:
  `column_name, table, consumer_name, consumer_type, last_used, query_count`.
- **Aggregate to the same grain the catalog uses** (`JOIN_GRAIN`, default
  `column_name`): group usage rows by that key, dedup consumers by
  `(consumer_name, consumer_type)`, taking `MAX(last_used)` and
  `SUM(query_count)` per consumer.
- Produce, per catalog entry, a `consumers` value: a list of dicts
  `{"name": str, "type": str, "last_used": str|None, "query_count": int|None}`,
  sorted by `query_count` descending then name. Empty list when a column has no
  recorded usage.
- **Join into `load_catalog()`** so every entry gets a `consumers` list. Columns
  with no usage get `[]`.
- **Graceful degradation:** if `USAGE_ENABLED` is False, or the usage source is
  missing/unreachable/empty, do NOT crash — set `consumers = []` for all entries
  and record the reason in the health report. The rest of the catalog must load
  normally.

## Canonical contract — one additive change
- Add `consumers` to `CANONICAL_FIELDS` (append it; keep every existing field and
  its type unchanged). Every code path that builds a catalog row must populate
  `consumers` (default `[]`). This is the only contract change permitted.

## Synthetic data — sample_data/usage.csv + generator
- Extend `sample_data/_generate.py` to emit `usage.csv` with columns:
  `column_name, table, consumer_name, consumer_type, last_used, query_count`.
- Make it realistic and varied:
  - Consumer types spanning at least: `Streamlit app`, `dbt model`,
    `Dashboard`, `Scheduled query`, `User / ad-hoc`.
  - Some columns are **load-bearing** (many consumers, high counts, recent
    `last_used`); some have **one** consumer; several documented columns have
    **no** usage rows at all (so the empty state is visible).
  - `last_used` dates spread across the last ~9 months (a few very stale) so a
    later "is it still used" evolution has data to work with.
- Only reference columns that exist in the synthetic `structure.csv` so the join
  produces real matches.

## app.py — surface consumers in the detail panel
- In the column detail panel, add a **"Used by"** section directly beneath the
  existing "Used in N tables" reverse index. Keep the existing structure section
  as-is.
- Render each consumer as a row: consumer name + a small type badge (color the
  badge by type). If `last_used` / `query_count` are present, show them quietly
  as secondary text (e.g. "last read 3 days ago · 412 queries") — small, not the
  headline.
- Empty state: if `consumers` is empty, show a subtle line like
  "No recorded consumers" (and, if usage is disabled/unavailable per the health
  report, "Usage data not available in this environment"). Never error.
- Style consistent with the current navy/gold detail panel. Use a visually
  distinct accent from the gold table reverse-index so the two lists don't blur
  together.
- Respect `USAGE_ENABLED`: when False, omit the "Used by" section entirely.

## The ACCESS_HISTORY query template (default value for USAGE_QUERY)
This is a **starting template**, not guaranteed-final SQL — the JSON paths and
the consumer-labeling heuristic must be validated against real `ACCESS_HISTORY`
on SiS. Include it as the default and add a comment saying so.

```sql
SELECT
    cols.value:"columnName"::string   AS column_name,
    obj.value:"objectName"::string    AS table_name,
    COALESCE(qh.query_tag, ah.user_name) AS consumer_name,
    CASE
        WHEN qh.query_tag ILIKE '%streamlit%' THEN 'Streamlit app'
        WHEN qh.query_tag ILIKE '%dbt%'       THEN 'dbt model'
        WHEN qh.query_tag ILIKE '%tableau%'
          OR qh.query_tag ILIKE '%powerbi%'
          OR qh.query_tag ILIKE '%sigma%'     THEN 'Dashboard'
        WHEN qh.query_type = 'SELECT'
          AND qh.scheduled = TRUE             THEN 'Scheduled query'
        ELSE 'User / ad-hoc'
    END                                AS consumer_type,
    MAX(ah.query_start_time)::string   AS last_used,
    COUNT(*)                           AS query_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    ON ah.query_id = qh.query_id
, LATERAL FLATTEN(input => ah.base_objects_accessed) obj
, LATERAL FLATTEN(input => obj.value:"columns") cols
WHERE ah.query_start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND obj.value:"objectDomain"::string = 'Table'
GROUP BY 1, 2, 3, 4
```

Add a config comment near `USAGE_QUERY` noting: requires Enterprise Edition,
`IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`, and that `ACCESS_HISTORY` has
latency; the `query_tag`-based consumer labeling only works as well as the org's
query tagging (make the heuristic easy to edit).

## Acceptance
- With defaults (`USAGE_SOURCE = "local_csv"`, `USAGE_ENABLED = True`) the app
  runs with no Snowflake and shows a "Used by" list in the detail panel for
  columns that have synthetic usage, an empty state for those that don't.
- A load-bearing column (e.g. CUSIP) shows multiple consumers of different types;
  at least one documented column shows no consumers.
- Setting `USAGE_SOURCE = "access_history"` changes only which reader runs — no
  other code path changes (proves the seam); it is not required to execute now.
- `USAGE_ENABLED = False` cleanly hides all usage UI and skips the load.
- `CANONICAL_FIELDS` gains `consumers`; all existing fields/behaviour unchanged.
- Database names / paths / consumer heuristics live in `config.py`, not in
  `app.py` or hardcoded in `data.py` logic.

## Suggested order
1. config.py usage block + `USAGE_QUERY` template.
2. Extend `_generate.py`; generate `usage.csv`.
3. data.py: reader → normalize → aggregate to grain → join → graceful fallback;
   add `consumers` to `CANONICAL_FIELDS`.
4. app.py: "Used by" section + badges + empty state, gated on `USAGE_ENABLED`.
5. Run on synthetic data; verify acceptance criteria.
