# CLAUDE.md — TVS Sales Forecasting & AI Data Studio

Guidance for Claude Code (and humans) working in this repo. Read this first.

## What this project is
Full-stack sales-forecasting app.
- **Backend**: FastAPI + Pandas + scikit-learn + Optuna (`main.py`, `forecasting_engine.py`). Deployed on **Render**.
- **Frontend**: React + Vite + Recharts (`frontend/`). Deployed on **Vercel**.
- **GitHub repo (source of truth for deploys)**: https://github.com/AnkitJohari01/tvs-sales-dashboard
- **Live backend**: https://tvs-sales-dashboard.onrender.com  (API docs at `/docs`)

Two forecasting surfaces:
1. **Static dashboard** — pre-trained model artifacts (`*.pkl`, `model_metadata.json`).
2. **Data Studio (Dynamic AI Forecaster)** — upload any CSV; backend auto-detects date + target,
   engineers features, runs an Optuna model tournament, returns a forecast.

## ⚠️ CRITICAL: this local folder is NOT a git repo
This directory (`...tvs-sales-dashboard-main\tvs-sales-dashboard-main`) is an **unzipped GitHub ZIP**,
not a clone. It has **no git remote**. Editing files here does **NOT** change the live site.

Render deploys from the **GitHub repo**, not from this folder. To make any change go live you must get the
edited files into GitHub (Render + Vercel then auto-deploy on commit). Options:
- **GitHub web upload** (no git needed): `Add file → Upload files` into the matching folder; same
  filename + same folder = replaces the file. Backend files go in repo root; the Data Studio component
  goes in `frontend/src/components/DynamicForecast/`.
- Or clone the repo properly and `git push`.

Default branch may be `main` or `master` — check the repo's branch dropdown before using `/upload/main/...` URLs.

## How target/date detection works (the recurring issue)
The Data Studio "wrong target column" complaints trace to auto-detection. Key code:
- `forecasting_engine.py` → `DataPreprocessor._find_best_numeric_column()` — picks the forecast target.
  It is **name-aware**: columns whose names match `TARGET_NAME_HINTS` (sales, revenue, amount, value,
  qty, price, …) rank first, then coefficient of variation breaks ties. ID-like names
  (`ID_NAME_PATTERNS`) are skipped. `suggest_target_column()` is the public wrapper.
- `main.py` → `/analyze-csv` returns `suggested_target` so the UI pre-selects the right column.
- `frontend/.../DynamicForecastUI.jsx` → on upload, defaults the dropdown to `suggested_target`
  (falls back to first-numeric only if absent).

Behavior notes:
- If the user picks a **categorical** column, the engine treats it as a **group_col** and auto-picks a
  numeric target (this is why "Tyresize (by ItemGroupName)" appeared — `Tyresize` is a numeric-looking
  attribute that beat the real measure under the OLD heuristic).
- For the demo dataset `FY2021_2025_SALES_DUMMY_500K.csv`, the real target is **`ValueBeforeGST`**
  (contains "value" → matches a hint). Date column is `InvoiceDate`.
- To extend detection for oddly-named measures, add keywords to `TARGET_NAME_HINTS`.

## Verifying a deploy actually shipped
The fastest tell: check whether the live API returns the new field.
```
curl -s -F "file=@FY2021_2025_SALES_DUMMY_500K.csv" \
  https://tvs-sales-dashboard.onrender.com/analyze-csv | grep suggested_target
```
- `"suggested_target":"ValueBeforeGST"` → new code is live.
- No `suggested_target` field → **OLD code still deployed** (upload/commit didn't land, or Render hasn't
  finished building — watch the service's **Events** tab, ~2–5 min).

## Deployment gotchas seen in this project
- **`ERR_HTTP2_PROTOCOL_ERROR` / "Failed to fetch"** on `/analyze-csv` = worker **OOM-killed** on Render's
  512 MB free tier while loading a large CSV. `/analyze-csv` is now memory-safe: streams a one-column
  chunked row count + builds stats from a bounded 100k-row **sample** (`sampled` flag in the response).
  Truly huge files may still strain 512 MB → bump Render RAM.
- **`ERR_NAME_NOT_RESOLVED`** = the Render host isn't resolving = service **suspended/deleted**, not a code
  bug. Fix in the Render dashboard (Resume / redeploy / recreate). A normal cold start still resolves (just
  slow ~50s), so a name-resolution failure is a service-state problem.
- If the backend URL ever changes, update the frontend env var **`VITE_API_URL`** in Vercel and redeploy;
  the frontend reads `import.meta.env.VITE_API_URL` (`DynamicForecastUI.jsx`).

## Run locally
Backend: `pip install -r requirements.txt` then `uvicorn main:app --reload` (→ http://localhost:8000).
Frontend: `cd frontend && npm install && npm run dev` (→ http://localhost:5173).
Python note: on this Windows machine, `python`/`python3` may hit the Microsoft Store shim and fail — use a
real interpreter/venv.

## Files that matter
- `main.py` — FastAPI app; endpoints incl. `/analyze-csv`, `/dynamic-forecast`, `/forecast`, filters.
- `forecasting_engine.py` — `DataPreprocessor`, `FeatureEngineer`, `ModelTournament`, `ForecastPipeline`.
- `frontend/src/components/DynamicForecast/DynamicForecastUI.jsx` — Data Studio UI.
- `model_metadata.json`, `winner_model.pkl`, `scaler.pkl`, etc. — static pre-trained artifacts.
- `requirements.txt`, `Dockerfile` — backend deploy config.
