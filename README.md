# TVS Sales Dashboard

🔗 Live: https://tvs-sales-dashboard.vercel.app/

## Business Use Case

Sales operations teams at TVS accumulate years of transaction-level data — by branch, customer, product, and sales rep — but lack a fast, honest way to turn that data into forward-looking revenue numbers. Spreadsheet models don't scale, and off-the-shelf BI tools either hide their error rates or require a data scientist to operate.

This app solves both problems with two forecasting surfaces in one place. The static dashboard delivers pre-trained forecasts with rich visualisations, an EDA explorer, and a deep-dive model audit that reports true WMAPE so planners know exactly how much to trust the numbers. The Dynamic Data Studio goes further: upload any time-series CSV and the backend auto-detects the date and target columns, engineers lag and rolling features, runs an Optuna-tuned model tournament across XGBoost, LightGBM, Ridge, and seasonal baselines, and returns a plain-English verdict alongside the forecast chart — no ML expertise required.

The result is self-serve forecasting that non-technical planners can operate daily, with honest accuracy reporting baked in so decisions rest on real confidence rather than false precision.

## How to Use

### Static Dashboard
1. Open https://tvs-sales-dashboard.vercel.app/
2. Use the **Forecast** section to set a start date and horizon, then submit to see the pre-trained model's output.
3. Scroll to **EDA Graphs** to explore historical trends (upload `FY2021_2025_SALES_DUMMY_500K.csv` when prompted).
4. Scroll to **Model Audit** for a full backtest report including WMAPE, allocation risk, and bias analysis.

### Dynamic Data Studio (AI Forecaster)
1. Scroll to the **Data Studio** section or click the nav link.
2. Click **Upload CSV** and select any time-series file.
3. The backend auto-detects the date column and suggests the best numeric target; confirm or change the dropdowns.
4. Optionally expand **Advanced Filters** to slice by branch, product, or any categorical column before forecasting.
5. Click **Run Forecast** and wait for the model tournament to complete (~30–60 s on cold start).
6. Review the forecast chart, WMAPE score, and plain-English AI verdict.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend framework | React 19 + Vite 8 |
| Charts | Recharts 3 |
| PDF export | jsPDF + html2canvas |
| CSV parsing | PapaParse |
| Backend API | FastAPI (Python 3.10) |
| Data processing | Pandas 2, NumPy |
| ML models | scikit-learn, XGBoost 2, LightGBM 4, Prophet, statsmodels |
| Hyperparameter tuning | Optuna 3 |
| LLM verdicts | Anthropic SDK (optional) |
| Frontend deploy | Vercel (static build via `@vercel/static-build`) |
| Backend deploy | Render (Docker / Python web service) |

## Deployment

### Prerequisites
- Python 3.10+, Node.js 18+
- A [Render](https://render.com) account (backend) and a [Vercel](https://vercel.com) account (frontend)
- The GitHub repo: https://github.com/AnkitJohari01/tvs-sales-dashboard

### Local development

```bash
# Backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload        # → http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                      # → http://localhost:5173
```

Copy `.env.example` to `.env` and fill in values before starting the backend:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables plain-English AI verdicts on `/explain-alert`; falls back to rule-based text if unset |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins; defaults to localhost ports |

### Backend — Render

1. In the Render dashboard, create a new **Web Service** and connect the GitHub repo.
2. Set **Environment** to `Python`, or use the provided `Dockerfile` for a Docker deploy.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables (`ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS`) under **Environment** in the service settings.
6. Deploy. The live URL will be something like `https://tvs-sales-dashboard.onrender.com`.

> **Note:** The free Render tier has 512 MB RAM. The `/analyze-csv` endpoint is memory-safe (bounded 100 k-row sample), but very large files may still cause OOM kills — upgrade the plan if needed. Cold starts take ~50 s; `ERR_NAME_NOT_RESOLVED` means the service is suspended, not a code bug.

### Frontend — Vercel

1. In the Vercel dashboard, import the GitHub repo.
2. Set **Root Directory** to `frontend`.
3. Add the environment variable:
   - **Key:** `VITE_API_URL`
   - **Value:** your live Render backend URL (e.g. `https://tvs-sales-dashboard.onrender.com`)
4. Deploy. Vercel runs `vite build` and serves the `dist/` output.

> If the backend URL ever changes, update `VITE_API_URL` in Vercel's project settings and redeploy the frontend.

### Verify the deploy shipped

```bash
curl -s -F "file=@FY2021_2025_SALES_DUMMY_500K.csv" \
  https://tvs-sales-dashboard.onrender.com/analyze-csv | grep suggested_target
```

`"suggested_target":"ValueBeforeGST"` confirms the latest backend code is live.
