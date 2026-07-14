# Implementation Plan — Change Forecast Target After Generation

Maps the functional spec (re-target vs. re-segment) to the actual endpoints and
React components in this repository. Two modes:

- **Mode A — Re-target (recompute):** new numeric measure (e.g. Sales → Revenue).
  Requires a pipeline re-run. Explicit, button-triggered.
- **Mode B — Re-segment (filter):** view the *same* forecast by a categorical
  dimension (Branch / Customer / Product). Live, in-memory, no re-run.

Legend: **[FE]** frontend, **[BE]** backend. Effort in ideal dev-hours (rough).

---

## 0. Current state (verified)

Backend `main.py`
- `POST /analyze-csv (file)` → columns[{name,dtype,is_numeric,unique_count}], detected_date_column, date_range.
- `POST /dynamic-forecast (file, target_col, group_col?)` → forecast, models_leaderboard, winner, ai_summary, metadata. **Re-uploads the whole file each call. Aggregates to ONE series — no segment grain.**
- `POST /forecast (…, branch?, customer?, product?)` → detailed segment-grain rows. Already filterable.
- `GET /filters` → branches, customers, products.

Engine `forecasting_engine.py`
- `ForecastPipeline.run(df, target_col, group_col, forecast_days)`.
- `DataPreprocessor`: categorical target ⇒ used as group_col + auto numeric target (basis for Mode B classification).

Frontend `DynamicForecast/DynamicForecastUI.jsx`
- State: file, fileName, targetColumn, datasetStats, isAnalyzing, isLoading, error, forecastData.
- `handleFileUpload` → /analyze-csv; `generateForecast` → /dynamic-forecast (re-uploads `file`).
- No upload/session cache; no request cancellation; no “stale result” state.

**Two structural gaps to close:** (1) no server-side dataset cache → re-target re-uploads
large files; (2) dynamic path has no segment breakdown → Mode B unsupported there.

---

## Phase 1 — Mode A correctness (no silent re-filter) · ~0.5 day · [FE]

Goal: changing the target never mutates displayed results in place; header/chart/table
never disagree.

1. **Stale-state tracking.** Add `committedTarget` (the target the current `forecastData`
   was computed with). Derive `isStale = forecastData && targetColumn !== committedTarget`.
   Set `committedTarget` on a successful `/dynamic-forecast` response.
   *File:* `DynamicForecastUI.jsx`.
2. **Resolution helper.** `resolveMode(col, datasetStats)` → `"A" | "B" | "noop"` using the
   `is_numeric` / `unique_count` already in `datasetStats.columns`. Numeric & ≠ committed → A;
   low-cardinality categorical → B; equal → noop.
3. **UI wiring.** When `isStale`: dim `.chart-card`/`.table-card`, overlay
   *“Showing forecast for {committedTarget} — re-run to update.”* Relabel the action button to
   **“Re-run forecast for {targetColumn}”**. Keep results visible (not blanked).
4. **Acceptance:** switching target dropdown updates nothing until re-run; no mixed-state labels.

Risk: low. Pure FE. No contract change.

---

## Phase 2 — Server-side dataset cache (kill the re-upload) · ~1 day · [BE]+[FE]

Goal: re-targeting sends `{upload_id, target_col}`, not the whole file.

1. **[BE] Cache on analyze.** In `/analyze-csv`, after `pd.read_csv`, store the DataFrame in a
   TTL cache keyed by a generated `upload_id` (uuid4). Return `upload_id` in the response.
   *Impl:* module-level `dict` + timestamp, or `cachetools.TTLCache(maxsize=N, ttl=3600)`.
   Guard memory: cap rows / evict LRU (dataset can be large).
2. **[BE] New recompute route.** `POST /dynamic-forecast/rerun (upload_id, target_col, group_col?)`
   → look up cached df, run `ForecastPipeline.run(...)`, same response shape as `/dynamic-forecast`.
   Return 410/“upload expired” if the key is gone → FE falls back to re-upload.
3. **[FE] Use it.** Store `datasetStats.upload_id`. `generateForecast` posts to `/rerun` when an
   `upload_id` exists, else the existing multipart path. On 410, transparently re-upload.
4. **Acceptance:** second+ forecasts on the same file transfer only JSON; cold-cache still works.

Risk: medium — memory management. Mitigate with TTL + size cap + LRU eviction; document in README.

---

## Phase 3 — Robust re-target validation · ~0.5 day · [BE]

Goal: malformed/low-coverage targets fail loud and specific, never a silent forecast / generic 500.

1. **Pre-flight in pipeline or route.** Before running, compute for `target_col`:
   non-null coverage, numeric-parse rate (`pd.to_numeric(errors="coerce")`), row count after clean.
2. **Rules.**
   - parse rate < 0.5 → 422 `"'{col}' isn't numeric — {x}% couldn't be parsed."` (or auto-route to Mode B if categorical).
   - non-null < 0.5 → 422 with coverage figure.
   - rows < engine minimum (lag/rolling guard) → 422 `"Not enough history after cleaning ({n} rows)."`
   - ID/high-cardinality name heuristics already in `DataPreprocessor` → reject as target.
3. **[FE] Surface** these as the dismissible inline error (already standardized).
4. **Acceptance:** each edge case returns a distinct, actionable message; covered by tests (Phase 6).

Risk: low. Reuses existing engine heuristics.

---

## Phase 4 — Mode B: segment breakdown + live filter · ~2–3 days · [BE]+[FE]

Goal: view the same forecast by Branch/Customer/Product with sub-200ms, no re-run.
This is the larger gap — the dynamic path currently returns only an aggregate series.

Backend (pick one):
- **4a (preferred): segment-grain output.** Extend `ForecastPipeline` to optionally forecast per
  group when a categorical dimension is present (it already resolves group_col). Response gains
  `forecast_by_segment` or a `segment` column per row, plus `available_segments`.
  Reuse the top-N + “Other (aggregated)” capping already used in `/forecast` to bound size.
- **4b (fallback): reuse `/forecast` + `/filters`.** If Mode B is only needed for the pretrained
  Sales model, drive the existing filterable `/forecast` (branch/customer/product) instead of
  reimplementing on the dynamic path. Cheaper, but limited to that model’s target.

Frontend:
1. **Segment filter bar** (dependent dropdowns Dimension → Value, multi-select, active-filter chips,
   “Clear all”), shown only when `available_segments` exists.
2. **In-memory filter+aggregate** of `forecast_by_segment` by date; recompute totals, confidence
   band, summary. Debounce ~150ms. Empty result → empty-state, keep chips.
3. **Guardrail:** if segment rows are very large, filter/aggregate server-side (query param) instead
   of shipping all rows (detailed grain can reach ~1.7M rows).
4. **Acceptance:** filter updates <200ms, never triggers a model run; totals reconcile to the
   unfiltered series when “All”.

Risk: medium-high (new engine output path + payload size). Phase behind 1–3; can ship 4b first.

---

## Phase 5 — Race safety & caching · ~0.5 day · [FE]

1. **AbortController / request token** on both recompute and filter calls; ignore stale responses so a
   later selection can’t be overwritten by an earlier run.
2. **Result memo** `Map<`upload_id|target`, result>` for instant “Revert” and toggling between two
   measures. Add a **“Revert to previous forecast.”**
3. **Acceptance:** rapid double target-change never leaves stale results; revert is instant.

Risk: low.

---

## Phase 6 — Tests & docs · ~0.5–1 day

- **[BE] pytest:** cache set/get/expiry; `/rerun` happy path + expired key (410); validation 422s
  (non-numeric, low-coverage, too-few-rows, ID column). Extend existing `test_*` style.
- **[FE]:** resolveMode unit cases; stale-state + relabel behavior; filter aggregation math.
- **Docs:** README section on the cache (memory/TTL), the two modes, and the new endpoints.

---

## Sequencing & shippable increments

| Increment | Phases | Ships |
|---|---|---|
| MVP correctness | 1, 3 | No more silent/mixed-state target changes; validated re-target on existing (re-upload) path. |
| Performance | 2, 5 | No re-upload, cancellation, instant revert. |
| Full feature | 4 (+6) | True live segment filtering (Mode B). |

Phases 1 and 3 are independent and can land immediately. Phase 2 unblocks the best UX for A.
Phase 4 is the only heavy lift and is isolated — defer or descope to 4b without blocking the rest.

---

## Data-contract changes (summary)

- `/analyze-csv` response: **+ `upload_id`**.
- New `POST /dynamic-forecast/rerun {upload_id, target_col, group_col?}` (same response shape).
- Re-target validation errors standardized to **HTTP 422** with a specific `detail`.
- (Phase 4) forecast response: **+ `available_segments`, + segment grain** (`forecast_by_segment` or per-row `segment`).

## Top risks

1. **Cache memory blow-up** (large CSVs) → TTL + size cap + LRU, documented.
2. **Mode B payload size** → server-side filter/top-N capping, reuse `/forecast` pattern.
3. **Scope creep from conflating A/B** → the mode resolver (Phase 1) is the guardrail; keep them separate in code and UI.
