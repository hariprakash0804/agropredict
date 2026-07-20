# AgroPredict Frontend: Next.js Interactive Dashboard

This is the Next.js React frontend application for the AgroPredict platform. It provides a dark-themed, glassmorphic dashboard featuring interactive time-series charts, AI advisories, export capabilities, and an AI chat interface.

## 🛠️ Technology Stack
* **Next.js**: React framework with App Router.
* **TypeScript**: Type safety across interfaces and props.
* **TailwindCSS**: Premium responsive styles and glassmorphism.
* **Recharts**: Interactive charting library for price quantile forecasts and weather covariates.
* **Lucide React**: Vector icons library.
* **Vercel**: Automated serverless edge deployment.

---

## 🎨 Layout & Components

### 1. Header & Navigation
* **Brand Logo**: Branding featuring dynamic animation.
* **Enter Custom Parameters Toggle**: Switches between the seeded default combinations and a custom selection form.
* **Auth Options**: Sign in and Sign out actions, storing the active user session in localStorage.

### 2. Custom Parameters Ribbon
* Displays options to select States, Districts, Mandis, Commodities, Varieties, and Grades.
* Dynamically narrows down districts, mandis, varieties, and grades based on the parent selection.
* Includes custom Date Range picks and a green **Run Ingestion & Predict** execution button.

### 3. Charts & Analytics
* **Price Quantile Chart**: Visualizes actual historical prices (solid line) and future forecasts with p10-p90 shaded confidence bands and p50 median forecasts (dashed lines).
* **Weather Outlook Chart**: Dual-axis weather combination plotting (Max/Min Temperatures as lines, Rainfall precipitation as bar blocks).
* **SVG Exporters**: Exports both price and weather charts as high-resolution, vector-format SVGs with pre-styled dark themes and proper coordinate clipping.
* **Excel Exporter**: Downloads full tabular history and forecast records as a standard `.xls` spreadsheet.

### 4. AI Advisor Panels
* **Farmer Selling Advisory**: Displays suggested strategies (e.g. Sell immediately) and custom textual reasoning.
* **Trader / Procurement Advisory**: Displays supply-chain guidance (e.g. Spot buying).
* **Weather Risk Markers**: Shakes and alerts users based on rainfall and heat stress danger index thresholds.

---

## 🚀 Setup & Execution

### 1. Configure API Base URL
Create a `.env.local` file in the `frontend/` directory:
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 2. Run Dashboard
```bash
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to interact with the platform.
