# AgroPredict Backend: FastAPI Analytics & Ingestion Engine

This is the Python-based backend server for the AgroPredict platform. It exposes REST API endpoints for historical price data, forecasting, chatbot advisory, and location-metadata hierarchies.

## 🛠️ Technology Stack
* **FastAPI**: High-performance Python framework for building REST APIs.
* **SQLAlchemy & Asyncmy**: Asymmetric asynchronous database connections and ORM queries for MySQL/MariaDB database.
* **Alembic / Startup Schema Checker**: Automatic schema checking and self-healing migrations on startup.
* **Pandas**: Used for formatting historical series datasets, matching structures, and merging weather covariates.
* **HuggingFace Chronos-2 (via OpenRouter/fallback)**: Zero-shot quantile forecasting for time-series modal prices.
* **OpenRouter**: Integrates the `openrouter/free` LLM to dynamically generate Farmer & Trader supply chain advisories.
* **APScheduler**: Manages background scheduled tasks (such as pre-caching or periodic price ingestion).

---

## 📈 API Endpoints

### 1. Metadata & Hierarchy
* `GET /api/metadata/agmarknet`
  Returns the complete hierarchical mapping of Indian States -> Districts -> Mandis, along with the list of supported commodities.

### 2. Historical Prices & Weather Ingestion
* `GET /api/history/{commodity_slug}/{mandi_name}`
  Accepts query parameters: `state`, `district`, `start_date`, `end_date`, `variety`, `grade`.
  * **Ingestion Flow**: If no records exist in the database, it dynamically queries `data.gov.in`'s historical and daily resources using properly cased filter payloads (e.g. `filters[State]`, `filters[Variety]`, etc.).
  * Automatically saves new records to the database with corresponding variety and grade columns.
  * Fetches historical weather (max/min temp, precipitation) from local climate records.

### 3. Price Forecasting & AI Advisories
* `GET /api/forecast/{commodity_slug}/{mandi_name}`
  Accepts query parameters: `state`, `district`, `horizon` (default 30 days), `variety`, `grade`.
  * Generates future price quantiles (p10, p50, p90) using zero-shot quantile forecasting models.
  * Compiles price, location, weather, and variety/grade details, and queries OpenRouter to generate tailored advisories:
    * **Farmer Advisory**: Strategy (e.g. Sell immediately vs. Store harvest) and custom reasoning.
    * **Trader/Procurement Advisory**: Strategy (e.g. Contract buying vs. Spot market) and custom reasoning.
    * **Weather Risks**: Rainfall disruption risk levels and Heat stress risk levels.

### 4. Interactive Chatbot Advisor
* `POST /api/chat`
  Accepts a JSON payload containing the user's question, historical prices, forecast p50, and weather covariates.
  Returns an AI response that answers the user's agricultural and economic queries with live context.

---

## 🚀 Setup & Execution

### Prerequisite Environment Variables (`.env`)
Create a `.env` file in the `backend/` directory:
```env
DATABASE_URL=mysql+asyncmy://username:password@host:port/database_name
OPENROUTER_API_KEY=your-openrouter-api-key
DATAGOV_API_KEY=your-datagov-api-key
PORT=8000
```

### Run Server
```bash
pip install -r requirements.txt
python app.py
```
The server will run on `http://0.0.0.0:8000` with hot-reload or background logs.
