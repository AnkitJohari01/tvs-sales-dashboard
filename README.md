# TVS Sales Forecasting & AI Data Studio 📊

Welcome to the **TVS Sales Forecasting App**! This repository houses a full-stack application (React + FastAPI) designed to bring enterprise-grade machine learning to sales forecasting. 

Whether you're looking at static historical data or uploading brand new CSVs on the fly, this app automatically engineers features, trains multiple models, and provides plain-English verdicts on your data.

---

## 🚀 Key Features

### 1. 🧠 Dynamic Data Studio (AI Forecaster)
Upload *any* time-series CSV, and the backend engine will take over:
- **Auto-Detection**: Automatically detects your date columns and available targets.
- **Dynamic Slicing**: Want to forecast a specific branch or product? Use the **Advanced Filters** to slice the dataset on the fly before forecasting.
- **Model Tournament**: The engine uses **Optuna** to run a hyperparameter-tuned tournament across multiple models (XGBoost, LightGBM, Ridge, plus fast baselines like Seasonal Naive).
- **Honest AI Verdicts**: Get a plain-English summary (e.g., *"projected to stay rising, averaging about 10k per period with moderate confidence"*).
- **Accurate Error Metrics**: We report true WMAPE (Weighted Mean Absolute Percentage Error) to give you an honest look at the model's reliability.

### 2. 📈 Interactive Dashboards
- **Pre-trained Forecasts**: View the pre-computed static forecasts with rich chart visualizations.
- **EDA Graphs**: Explore your data through interactive charts (requires the raw data file).
- **Model Audit**: An honest, deep-dive evaluation report of the static model, detailing allocation risks, backtest performance, and bias.

---

## 🏗️ Architecture

- **Frontend**: React + Vite + Recharts. A snappy, modern dashboard with dark mode and dynamic UI components.
- **Backend**: FastAPI + Pandas + Scikit-Learn + Optuna. A highly optimized, asynchronous Python backend designed to run ML models efficiently even in constrained environments (like Render).

---

## 💻 How to Run Locally

### Prerequisites
- Python 3.9+
- Node.js 18+

### 1. Start the Backend
```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Run the FastAPI server
uvicorn main:app --reload
```
The backend will be available at `http://localhost:8000`.

### 2. Start the Frontend
Open a new terminal window:
```bash
cd frontend

# Install dependencies
npm install

# Run the Vite development server
npm run dev
```
The frontend will be available at `http://localhost:5173`.

---

## ☁️ Deployment Guide

### Backend (Render)
1. Connect your GitHub repository to Render as a **Web Service**.
2. **Environment**: Python
3. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Render will automatically assign the port and provide a live URL.

### Frontend (Vercel)
1. Connect your GitHub repository to Vercel.
2. Select the `frontend` directory as the Root Directory.
3. In the Vercel project settings, add an Environment Variable:
   - **Key**: `VITE_API_URL`
   - **Value**: Your live Render backend URL (e.g., `https://your-api.onrender.com`)
4. Deploy! Vercel will build the Vite app and route all API requests to your live backend.

---

## 🔒 Security
- `.env` and `settings.json` are gitignored to prevent accidental credential leaks.
- If you use the LLM explanation features, ensure you set the `ANTHROPIC_API_KEY` in your `.env` or deployment environment variables.
