# AgroPredict: Covariate-Informed Mandi Price & Weather Forecasting Platform

AgroPredict is a premium, full-stack analytics platform that provides data-driven insights and AI advisories for agricultural commodities across markets (mandis) in India. By leveraging zero-shot quantile forecasting models (Chronos-2), historical weather metrics, and dynamic API ingestion, AgroPredict empowers farmers, traders, and agricultural analysts to forecast commodity prices, understand risk factors, and optimize their supply chains.

## 🚀 Key Features

* **Zero-Shot Quantile Price Forecasting**: Incorporates Chronos-2 models to forecast price trends 30 days into the future, providing p10, p50, and p90 confidence bounds.
* **Weather & Climate Covariates**: Integrates dual-axis historical and forecasted weather charts (Max/Min Temperature, Rain) to predict climate risks.
* **Dynamic Government Data Ingestion**: Seamlessly fetches real-time mandi prices directly from the Open Government Data API (`data.gov.in`) with automated fallback heuristics.
* **Custom Parameter Selection Ribbon**: Offers granular options to search across all Indian States, Districts, Mandis, Commodities, Varieties, and Grades.
* **Dynamic AI Farmer & Trader Advisories**: Generates contextual, supply-chain strategies and risk assessments (Rainfall Disruption, Heat Stress) powered by OpenRouter LLMs.
* **Premium SVG Exporter**: Supports downloading vector-format price and weather charts with dark-themed templates.
* **Excel Data Downloader**: Exports full historical price, weather, and forecasting data in standard spreadsheet formats.
* **Interactive AI Chatbot Advisor**: Allows users to chat directly with an LLM that is pre-loaded with the active query's price and weather context.

---

## 📂 Project Architecture

The repository is structured as a decoupled monorepo:

```
agropredict/
├── backend/            # FastAPI Backend (Python)
│   ├── app/
│   │   ├── api/        # REST Endpoints (History, Forecast, Accuracy, Chat)
│   │   ├── core/       # Database config & settings
│   │   ├── forecasting/# Chronos-2 Model & weather covariates logic
│   │   └── models/     # SQLAlchemy Database schemas
│   ├── app.py          # Uvicorn starting point
│   └── requirements.txt
└── frontend/           # Next.js Frontend (TypeScript & TailwindCSS)
    ├── src/
    │   └── app/        # Page layout & interactive dashboard
    ├── package.json
    └── next.config.ts
```

---

## 🛠️ Quick Start

### 1. Backend Setup
1. Navigate to the `backend/` directory.
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables in `.env` (API keys, OpenRouter, Database URI).
5. Start the development server:
   ```bash
   python app.py
   ```

### 2. Frontend Setup
1. Navigate to the `frontend/` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Open [http://localhost:3000](http://localhost:3000) to view the platform.

---

## 🌐 Deployments
* **Backend Hosting**: Deployed on **Render** (via ASGI Uvicorn server).
* **Frontend Hosting**: Deployed on **Vercel** (fully optimized Next.js serverless architecture).
