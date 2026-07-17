"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  TrendingUp,
  CloudRain,
  Thermometer,
  ShieldCheck,
  TrendingDown,
  User,
  Building,
  Activity,
  Layers,
  ChevronRight,
  Search,
} from "lucide-react";

interface PriceObs {
  date: string;
  min_price: number;
  max_price: number;
  modal_price: number;
  arrival_qty: number | null;
}

interface WeatherObs {
  date: string;
  temp_max: number;
  temp_min: number;
  precipitation_mm: number;
}

interface ForecastRes {
  commodity: string;
  mandi: string;
  horizon: number;
  forecast_dates: string[];
  p10: number[];
  p50: number[];
  p90: number[];
  weather_covariates: WeatherObs[];
}

interface AccuracyObs {
  eval_date: string;
  model_name: string;
  horizon: number;
  mae: number;
  rmse: number;
  mape: number;
}

// Normalize API URL to ensure it always ends with /api
const getApiUrl = () => {
  let url = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  url = url.trim().replace(/\/+$/, ""); // remove trailing slashes
  if (!url.endsWith("/api")) {
    url += "/api";
  }
  return url;
};
const API_BASE_URL = getApiUrl();

export default function Home() {
  const [commodities, setCommodities] = useState<{ id: number; name: string; slug: string }[]>([]);
  const [mandis, setMandis] = useState<{ id: number; name: string; state: string; district: string }[]>([]);
  
  // User Auth & History States
  interface UserSession {
    id: number;
    username: string;
  }
  interface SavedQuery {
    id: number;
    commodity_slug: string;
    mandi_name: string;
    state: string;
    district: string;
    start_date: string;
    end_date: string;
    created_at: string;
  }

  const [user, setUser] = useState<UserSession | null>(null);
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([]);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authUsername, setAuthUsername] = useState<string>("");
  const [authPassword, setAuthPassword] = useState<string>("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(false);

  // Check localstorage on load
  useEffect(() => {
    const saved = localStorage.getItem("agropredict_user");
    if (saved) {
      try {
        const u = JSON.parse(saved);
        setUser(u);
      } catch (e) {
        localStorage.removeItem("agropredict_user");
      }
    }
  }, []);

  // Load user query history
  const fetchUserHistory = async (userId: number) => {
    try {
      const res = await fetch(`${API_BASE_URL}/users/${userId}/logs`);
      if (res.ok) {
        const data = await res.json();
        setSavedQueries(data);
      }
    } catch (e) {
      console.error("Error fetching user history", e);
    }
  };

  useEffect(() => {
    if (user) {
      fetchUserHistory(user.id);
    }
  }, [user]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authUsername.trim() || !authPassword.trim()) {
      setAuthError("All fields are required.");
      return;
    }
    setAuthLoading(true);
    setAuthError(null);

    const path = authMode === "login" ? "login" : "register";
    try {
      const res = await fetch(`${API_BASE_URL}/auth/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: authUsername, password: authPassword })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Authentication failed.");
      }

      const data = await res.json();
      if (authMode === "login") {
        const session = { id: data.user_id, username: data.username };
        setUser(session);
        localStorage.setItem("agropredict_user", JSON.stringify(session));
      } else {
        // Success register -> auto login
        setAuthMode("login");
        // Trigger login request
        const loginRes = await fetch(`${API_BASE_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: authUsername, password: authPassword })
        });
        if (loginRes.ok) {
          const loginData = await loginRes.json();
          const session = { id: loginData.user_id, username: loginData.username };
          setUser(session);
          localStorage.setItem("agropredict_user", JSON.stringify(session));
        }
      }
      setAuthUsername("");
      setAuthPassword("");
    } catch (err: any) {
      setAuthError(err.message || "An authentication error occurred.");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSignOut = () => {
    setUser(null);
    setSavedQueries([]);
    localStorage.removeItem("agropredict_user");
  };
  
  // Selection States
  const [selectedCommodity, setSelectedCommodity] = useState<string>("onion");
  const [selectedMandi, setSelectedMandi] = useState<string>("Sooramangalam");
  
  // Custom Query Fields (for all states, districts, and any custom commodities/mandis)
  const [useCustom, setUseCustom] = useState<boolean>(false);
  const [customCommodity, setCustomCommodity] = useState<string>("");
  const [customMandi, setCustomMandi] = useState<string>("");
  const [stateName, setStateName] = useState<string>("Tamil Nadu");
  const [districtName, setDistrictName] = useState<string>("Salem");
  
  // Date selection states
  const [startDate, setStartDate] = useState<string>(
    new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );

  const [horizon, setHorizon] = useState<number>(30);
  const [perspective, setPerspective] = useState<"farmer" | "trader">("farmer");
  
  // Response states
  const [history, setHistory] = useState<{ prices: PriceObs[]; weather: WeatherObs[] } | null>(null);
  const [forecast, setForecast] = useState<ForecastRes | null>(null);
  const [accuracy, setAccuracy] = useState<AccuracyObs[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Chatbot Advisor States
  const [chatQuery, setChatQuery] = useState<string>("");
  const [chatReply, setChatReply] = useState<string>("");
  const [chatLoading, setChatLoading] = useState<boolean>(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const submitChat = async () => {
    if (!chatQuery.trim() || !history || !forecast) return;
    setChatLoading(true);
    setChatError(null);
    try {
      const commName = useCustom ? customCommodity : (commodities.find(c => c.slug === selectedCommodity)?.name || selectedCommodity);
      const mandiName = useCustom ? customMandi : selectedMandi;
      
      const payload = {
        question: chatQuery,
        history_prices: history.prices.map(p => ({ date: p.date, modal_price: p.modal_price })),
        forecast_p50: forecast.p50,
        forecast_dates: forecast.forecast_dates,
        weather_covariates: forecast.weather_covariates.map(w => ({
          date: w.date,
          temp_max: w.temp_max,
          temp_min: w.temp_min,
          precipitation_mm: w.precipitation_mm
        })),
        commodity: commName,
        mandi: mandiName,
      };

      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to fetch response from AI Advisor.");
      }

      const data = await res.json();
      setChatReply(data.reply);
      setChatQuery("");
    } catch (err: any) {
      console.error(err);
      setChatError(err.message || "An error occurred while calling the AI advisor.");
    } finally {
      setChatLoading(false);
    }
  };

  // Export Data as CSV
  const downloadCSV = () => {
    if (!history || !forecast) return;
    
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "Date,Type,Actual Price (INR),Forecast p10 (INR),Forecast p50 (INR),Forecast p90 (INR),Max Temp (C),Precipitation (mm)\n";
    
    // Add history
    history.prices.forEach((p) => {
      csvContent += `${p.date},Historical,${p.modal_price},,,,\n`;
    });
    
    // Add forecast
    forecast.forecast_dates.forEach((d, i) => {
      const w = forecast.weather_covariates[i] || {};
      csvContent += `${d},Forecast,,${Math.round(forecast.p10[i])},${Math.round(forecast.p50[i])},${Math.round(forecast.p90[i])},${w.temp_max || ""},${w.precipitation_mm || ""}\n`;
    });
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `agropredict_${forecast.commodity.toLowerCase()}_${forecast.mandi.toLowerCase().replace(/\s+/g, '_')}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export AI Advisor Chat & Advisory as Text Report
  const downloadChatReport = () => {
    if (!forecast) return;
    
    let textContent = `AgroPredict Agricultural Report\n`;
    textContent += `Commodity: ${forecast.commodity}\n`;
    textContent += `Mandi: ${forecast.mandi}\n`;
    textContent += `Generated At: ${new Date().toLocaleString()}\n`;
    textContent += `=========================================\n\n`;
    
    textContent += `1. SELLING / PROCUREMENT STRATEGY:\n`;
    if (perspective === "farmer") {
      textContent += insights.trend === "up" 
        ? `Farmer strategy: Hold Crop (prices forecasted to rise by ${insights.changePct.toFixed(1)}%)\n`
        : `Farmer strategy: Sell Immediately (prices expected to decline/stay stable)\n`;
    } else {
      textContent += insights.trend === "up"
        ? `Trader strategy: Lock Futures Contracts (prices forecasted to rise by ${insights.changePct.toFixed(1)}%)\n`
        : `Trader strategy: Procure Spot Market (prices trending down)\n`;
    }
    
    textContent += `\nMarket Volatility: ${insights.volatility}\n`;
    
    if (chatReply) {
      textContent += `\n2. AI ASSISTANT CHAT HISTORY:\n`;
      textContent += `AI Reply: ${chatReply}\n`;
    }
    
    const element = document.createElement("a");
    const file = new Blob([textContent], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = `agropredict_advisor_report.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  // Export Recharts SVG as file
  const downloadChartSVG = (selector: string, filename: string) => {
    const wrapper = document.querySelector(selector);
    if (!wrapper) return;
    const svg = wrapper.querySelector("svg");
    if (!svg) return;
    
    try {
      const serializer = new XMLSerializer();
      let source = serializer.serializeToString(svg);
      if(!source.match(/^<svg[^>]+xmlns="http\/\/www\.w3\.org\/2000\/svg"/)){
          source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
      }
      if(!source.match(/^<svg[^>]+xmlns:xlink="http\/\/www\.w3\.org\/1999\/xlink"/)){
          source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
      }
      
      const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (e) {
      console.error("Error exporting SVG", e);
    }
  };

  // Fetch initial dropdown metadata
  useEffect(() => {
    async function init() {
      try {
        const [cRes, mRes] = await Promise.all([
          fetch(`${API_BASE_URL}/commodities`),
          fetch(`${API_BASE_URL}/mandis`),
        ]);
        if (!cRes.ok || !mRes.ok) throw new Error("Failed to load metadata");
        const cData = await cRes.json();
        const mData = await mRes.json();
        setCommodities(cData);
        setMandis(mData);
        if (cData.length > 0) setSelectedCommodity(cData[0].slug);
        if (mData.length > 0) setSelectedMandi(mData[0].name);
      } catch (err) {
        console.error(err);
        setError("Unable to connect to backend server. Make sure FastAPI is running on port 8000.");
      }
    }
    init();
  }, []);

  // Fetch function based on current selection/custom values
  const handleQuery = async () => {
    setLoading(true);
    setError(null);

    // Slugify custom commodity if present
    const commSlug = useCustom 
      ? customCommodity.trim().toLowerCase().replace(/\s+/g, '-') 
      : selectedCommodity;
      
    const mandiVal = useCustom ? customMandi.trim() : selectedMandi;

    if (!commSlug || !mandiVal) {
      setError("Please fill out both commodity name and mandi location.");
      setLoading(false);
      return;
    }

    try {
      const urlParams = new URLSearchParams({
        state: stateName,
        district: districtName,
        start_date: startDate,
        end_date: endDate,
      });

      const [histRes, foreRes, accRes] = await Promise.all([
        fetch(`${API_BASE_URL}/history/${commSlug}/${mandiVal}?${urlParams.toString()}`),
        fetch(`${API_BASE_URL}/forecast/${commSlug}/${mandiVal}?state=${stateName}&district=${districtName}&horizon=${horizon}`),
        fetch(`${API_BASE_URL}/accuracy/${commSlug}?horizon=${horizon}`),
      ]);

      if (!histRes.ok || !foreRes.ok || !accRes.ok) {
        if (histRes.status === 400 || foreRes.status === 400) {
          throw new Error("No daily price records are available for this specific commodity/mandi combination on data.gov.in.");
        }
        throw new Error("Failed to query data from API.");
      }

      const histData = await histRes.json();
      const foreData = await foreRes.json();
      const accData = await accRes.json();

      setHistory(histData);
      setForecast(foreData);
      setAccuracy(accData);
      setError(null);

      // Save search log to user history if logged in
      if (user) {
        try {
          await fetch(`${API_BASE_URL}/users/${user.id}/logs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              commodity_slug: commSlug,
              mandi_name: mandiVal,
              state: stateName,
              district: districtName,
              start_date: startDate,
              end_date: endDate,
            })
          });
          fetchUserHistory(user.id);
        } catch (logErr) {
          console.error("Error logging search history:", logErr);
        }
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "An unexpected error occurred during ingestion and forecasting.");
    } finally {
      setLoading(false);
    }
  };

  // Run initial query when dropdowns load
  useEffect(() => {
    if (selectedCommodity && selectedMandi && !useCustom) {
      handleQuery();
    }
  }, [selectedCommodity, selectedMandi, horizon]);

  // Combine history and forecast for rendering
  const getChartData = () => {
    if (!history || !forecast) return [];
    
    // Take historical prices
    const histPoints = history.prices.map((p) => ({
      date: p.date,
      actual: p.modal_price,
      p50: null,
      p10_p90: null,
    }));
    
    // Forecast points
    const forePoints = forecast.forecast_dates.map((d, i) => ({
      date: d,
      actual: null,
      p50: Math.round(forecast.p50[i]),
      p10_p90: [Math.round(forecast.p10[i]), Math.round(forecast.p90[i])],
    }));
    
    return [...histPoints, ...forePoints];
  };

  // Weather combination chart data
  const getWeatherChartData = () => {
    if (!forecast) return [];
    return forecast.weather_covariates.map((w) => ({
      date: w.date,
      temp_max: w.temp_max,
      precip: w.precipitation_mm,
    }));
  };

  // Compute insights
  const getInsights = () => {
    if (!history || !forecast) return { trend: "neutral", changePct: 0, volatility: "Low", alert: null };
    
    const currentPrice = history.prices[history.prices.length - 1]?.modal_price || 0;
    const finalForecast = forecast.p50[forecast.p50.length - 1] || 0;
    
    const changePct = currentPrice ? ((finalForecast - currentPrice) / currentPrice) * 100 : 0;
    const trend = changePct > 5 ? "up" : changePct < -5 ? "down" : "neutral";
    
    const prices = history.prices.map(p => p.modal_price);
    const mean = prices.reduce((a,b)=>a+b, 0) / prices.length;
    const variance = prices.reduce((a,b)=>a + Math.pow(b-mean, 2), 0) / prices.length;
    const volatilityVal = Math.sqrt(variance) / mean;
    const volatility = volatilityVal > 0.15 ? "High" : volatilityVal > 0.08 ? "Moderate" : "Low";
    
    let alert = null;
    const futurePrecip = forecast.weather_covariates.reduce((sum, w) => sum + w.precipitation_mm, 0);
    if (futurePrecip > 50 && selectedCommodity === "tomato") {
      alert = {
        title: "Monsoon Inundation Warning",
        desc: "Heavy localized precipitation forecasted. Tomato yield risks transport delays and crop spoilage.",
        type: "warning"
      };
    } else if (volatility === "High") {
      alert = {
        title: "Extreme Price Instability",
        desc: "Mandi prices are showing high variance. Exercise caution when locking long-term procurement prices.",
        type: "info"
      };
    }
    
    return { trend, changePct, volatility, alert };
  };

  const insights = getInsights();

  if (!user) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col justify-center items-center font-sans p-6">
        <div className="w-full max-w-md p-8 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 backdrop-blur-md flex flex-col gap-6 shadow-xl">
          <div className="flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941" />
              </svg>
            </div>
            <h1 className="text-2xl font-black bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
              AgroPredict
            </h1>
            <p className="text-xs text-zinc-400">Chronos-2 Zero-Shot Price Forecasting System</p>
          </div>

          <form onSubmit={handleAuth} className="flex flex-col gap-4">
            <div className="flex bg-zinc-800 rounded-lg p-0.5 border border-zinc-700">
              <button
                type="button"
                onClick={() => { setAuthMode("login"); setAuthError(null); }}
                className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all ${authMode === "login" ? "bg-emerald-500 text-zinc-950" : "text-zinc-400"}`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setAuthMode("register"); setAuthError(null); }}
                className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all ${authMode === "register" ? "bg-emerald-500 text-zinc-950" : "text-zinc-400"}`}
              >
                Register
              </button>
            </div>

            {authError && (
              <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                {authError}
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-500">Username</label>
              <input
                type="text"
                placeholder="Enter username"
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                className="bg-zinc-805 border border-zinc-705 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-500">Password</label>
              <input
                type="password"
                placeholder="Enter password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="bg-zinc-805 border border-zinc-705 rounded-lg px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
            </div>

            <button
              type="submit"
              disabled={authLoading}
              className="w-full bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-500/50 text-zinc-950 font-bold py-2.5 rounded-xl text-xs transition-all shadow-lg shadow-emerald-500/10 cursor-pointer mt-2"
            >
              {authLoading ? "Authenticating..." : authMode === "login" ? "Sign In" : "Register & Start"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans">
      {/* Header */}
      <header className="border-b border-zinc-800/80 bg-zinc-900/40 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.306a11.95 11.95 0 015.814-5.518l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
                AgroPredict
              </h1>
              <p className="text-[10px] text-zinc-500 font-medium">COVARIATE-INFORMED FORECASTING</p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Custom Mode Toggle */}
            <label className="flex items-center gap-2 cursor-pointer text-xs bg-zinc-800/60 border border-zinc-700/50 px-3 py-1.5 rounded-lg select-none">
              <input 
                type="checkbox" 
                checked={useCustom}
                onChange={(e) => setUseCustom(e.target.checked)}
                className="rounded border-zinc-700 text-emerald-500 focus:ring-emerald-500" 
              />
              <span>Enter Custom Parameters</span>
            </label>

            {/* User Session and Sign Out */}
            <div className="flex items-center gap-2 text-xs text-zinc-400 bg-zinc-800/40 px-3 py-1.5 rounded-lg border border-zinc-700/50">
              <span className="font-semibold text-zinc-300">👋 {user.username}</span>
              <button
                onClick={handleSignOut}
                className="text-red-400 hover:text-red-350 ml-2 font-bold cursor-pointer"
              >
                Sign Out
              </button>
            </div>

            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Chronos-2 Active
            </div>
          </div>
        </div>
      </header>

      {/* Error State */}
      {error && (
        <div className="max-w-7xl mx-auto mt-6 px-6 w-full">
          <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <div>
              <p className="font-semibold">Query Issue</p>
              <p className="mt-1 text-zinc-400">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Main Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8 flex flex-col gap-6">
        
        {/* Controls Ribbon */}
        <section className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
          
          {useCustom ? (
            /* Custom Form for All Commodities/States/Districts/Dates */
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-6 gap-4 items-end">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Commodity</label>
                <input
                  type="text"
                  placeholder="e.g. Beans, Apple, Onion"
                  value={customCommodity}
                  onChange={(e) => setCustomCommodity(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">State</label>
                <input
                  type="text"
                  placeholder="e.g. Tamil Nadu"
                  value={stateName}
                  onChange={(e) => setStateName(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">District</label>
                <input
                  type="text"
                  placeholder="e.g. Salem"
                  value={districtName}
                  onChange={(e) => setDistrictName(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Mandi / Market</label>
                <input
                  type="text"
                  placeholder="e.g. Sooramangalam"
                  value={customMandi}
                  onChange={(e) => setCustomMandi(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                />
              </div>
            </div>
          ) : (
            /* Simple Dropdowns (Default Seeded List) */
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Commodity</label>
                <select
                  value={selectedCommodity}
                  onChange={(e) => setSelectedCommodity(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-200 outline-none focus:border-emerald-500"
                >
                  {commodities.map((c) => (
                    <option key={c.slug} value={c.slug}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Mandi Location</label>
                <select
                  value={selectedMandi}
                  onChange={(e) => setSelectedMandi(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm font-medium text-zinc-200 outline-none focus:border-emerald-500"
                >
                  {mandis.map((m) => (
                    <option key={m.id} value={m.name}>{m.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] uppercase font-bold tracking-wider text-zinc-400">Forecast Horizon</label>
                <div className="flex bg-zinc-800 rounded-lg p-0.5 border border-zinc-700">
                  {[7, 30].map((h) => (
                    <button
                      key={h}
                      onClick={() => setHorizon(h)}
                      className={`flex-1 py-1 rounded-md text-xs font-semibold transition-all ${horizon === h ? "bg-emerald-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200"}`}
                    >
                      {h} Days
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between border-t border-zinc-850 pt-4 gap-4">
            <div className="flex flex-wrap items-center gap-2">
              {/* Run Query Button */}
              <button
                onClick={handleQuery}
                disabled={loading}
                className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-500/50 text-zinc-950 font-bold px-5 py-2 rounded-xl text-xs transition-all shadow-lg shadow-emerald-500/10 cursor-pointer animate-fade-in"
              >
                <Search className="w-4 h-4" />
                {loading ? "Ingesting & Forecasting..." : "Run Ingestion & Predict"}
              </button>

              {/* Export Buttons */}
              {history && forecast && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={downloadCSV}
                    title="Download complete price and weather dataset as CSV"
                    className="flex items-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all"
                  >
                    📥 Download Data (CSV)
                  </button>
                  <button
                    onClick={downloadChatReport}
                    title="Download summary report and AI chat log"
                    className="flex items-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all"
                  >
                    📄 Download AI Report
                  </button>
                  <button
                    onClick={() => downloadChartSVG(".price-chart-container", "agropredict_price_forecast_chart.svg")}
                    title="Export the main forecast chart as standard vector SVG"
                    className="flex items-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer transition-all"
                  >
                    📈 Export Chart (SVG)
                  </button>
                </div>
              )}
            </div>

            {/* Perspective View Selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400">Advisory:</span>
              <button
                onClick={() => setPerspective("farmer")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border ${perspective === "farmer" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "border-zinc-800 text-zinc-400 hover:bg-zinc-800/40"}`}
              >
                <User className="w-3.5 h-3.5" />
                Farmer
              </button>
              <button
                onClick={() => setPerspective("trader")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border ${perspective === "trader" ? "bg-teal-500/10 border-teal-500/30 text-teal-400" : "border-zinc-800 text-zinc-400 hover:bg-zinc-800/40"}`}
              >
                <Building className="w-3.5 h-3.5" />
                Trader / Procurement
              </button>
            </div>
          </div>

        </section>

        {/* Dashboard Grid */}
        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center min-h-[400px]">
            <div className="w-10 h-10 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="mt-4 text-sm text-zinc-400 font-medium">Dynamically mapping indexes and running Chronos-2 zero-shot forecast...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Left & Center: Charts & Metrics */}
            <div className="lg:col-span-2 flex flex-col gap-6">
              
              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                
                {/* Current Price */}
                <div className="p-4 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Last Observed price</p>
                  <p className="text-2xl font-black mt-1 text-zinc-100">
                    ₹{history?.prices[history.prices.length - 1]?.modal_price || 0}
                    <span className="text-xs font-medium text-zinc-400">/Qtl</span>
                  </p>
                  <span className="text-[10px] text-zinc-500">From fetched daily records</span>
                </div>

                {/* Trend Forecast */}
                <div className="p-4 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{horizon}d Prediction Change</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    {insights.trend === "up" ? (
                      <TrendingUp className="w-5 h-5 text-emerald-400" />
                    ) : insights.trend === "down" ? (
                      <TrendingDown className="w-5 h-5 text-rose-400" />
                    ) : (
                      <Activity className="w-5 h-5 text-zinc-400" />
                    )}
                    <p className={`text-2xl font-black ${insights.trend === "up" ? "text-emerald-400" : insights.trend === "down" ? "text-rose-400" : "text-zinc-200"}`}>
                      {insights.changePct > 0 ? "+" : ""}{insights.changePct.toFixed(1)}%
                    </p>
                  </div>
                  <span className="text-[10px] text-zinc-500">Forecasted direction</span>
                </div>

                {/* Volatility Indicator */}
                <div className="p-4 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Price Volatility</p>
                  <p className={`text-2xl font-black mt-1 ${insights.volatility === "High" ? "text-amber-400" : insights.volatility === "Moderate" ? "text-yellow-500" : "text-emerald-400"}`}>
                    {insights.volatility}
                  </p>
                  <span className="text-[10px] text-zinc-500">Historical deviation score</span>
                </div>

              </div>

              {/* Price Forecast Area Chart */}
              <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-zinc-200">Price Trend & Zero-Shot Quantile Forecast</h3>
                    <p className="text-xs text-zinc-500">Dynamic history query plotted with forecast quantiles (p10, p50, p90)</p>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] font-semibold">
                    <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Actual</span>
                    <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500/20"></span> p10 - p90 Confidence</span>
                    <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-emerald-400 border-t border-dashed"></span> p50 Median</span>
                  </div>
                </div>

                <div className="h-[280px] w-full price-chart-container">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={getChartData()} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/>
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#71717a" fontSize={9} tickLine={false} />
                      <YAxis stroke="#71717a" fontSize={9} domain={["auto", "auto"]} tickLine={false} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46", borderRadius: "8px" }}
                        labelStyle={{ color: "#a1a1aa", fontSize: "11px", fontWeight: "bold" }}
                        itemStyle={{ fontSize: "12px" }}
                      />
                      <Area type="monotone" dataKey="actual" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorPrice)" name="Actual Price (₹)" connectNulls={false} />
                      <Area type="monotone" dataKey="p10_p90" stroke="none" fill="#10b981" fillOpacity={0.15} name="Quantile Envelope" connectNulls={false} />
                      <Line type="monotone" dataKey="p50" stroke="#34d399" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Median Prediction (p50)" connectNulls={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Weather Covariates Chart */}
              <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                <div>
                  <h3 className="text-sm font-bold text-zinc-200">Weather Covariate Outlook</h3>
                  <p className="text-xs text-zinc-500">Live forecast weather parameters loaded into Chronos-2 model</p>
                </div>
                <div className="h-[150px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={getWeatherChartData()} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" stroke="#71717a" fontSize={9} tickLine={false} />
                      <YAxis yAxisId="left" stroke="#38bdf8" fontSize={9} tickLine={false} label={{ value: "Temp (°C)", angle: -90, position: "insideLeft", fill: "#38bdf8", style: { fontSize: "9px" } }} />
                      <YAxis yAxisId="right" orientation="right" stroke="#60a5fa" fontSize={9} tickLine={false} label={{ value: "Rain (mm)", angle: 90, position: "insideRight", fill: "#60a5fa", style: { fontSize: "9px" } }} />
                      <Tooltip contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46", borderRadius: "8px" }} />
                      <Legend wrapperStyle={{ fontSize: "10px" }} />
                      <Line yAxisId="left" type="monotone" dataKey="temp_max" stroke="#38bdf8" strokeWidth={1.5} dot={false} name="Max Temp (°C)" />
                      <Line yAxisId="right" type="monotone" dataKey="precip" stroke="#60a5fa" strokeWidth={1.5} dot={false} name="Precipitation (mm)" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

            </div>

            {/* Right: Sidebar Insights */}
            <div className="flex flex-col gap-6">
              
              {/* Alert Banner */}
              {insights.alert && (
                <div className={`p-4 rounded-2xl border flex gap-3 text-xs ${insights.alert.type === "warning" ? "bg-amber-500/10 border-amber-500/20 text-amber-400" : "bg-teal-500/10 border-teal-500/20 text-teal-400"}`}>
                  <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                  <div>
                    <p className="font-bold">{insights.alert.title}</p>
                    <p className="mt-1 text-zinc-400 leading-relaxed">{insights.alert.desc}</p>
                  </div>
                </div>
              )}

              {/* Perspective View Cards */}
              <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                <div className="flex items-center gap-2 pb-3 border-b border-zinc-800">
                  {perspective === "farmer" ? (
                    <>
                      <User className="w-5 h-5 text-emerald-400" />
                      <h3 className="text-sm font-bold text-zinc-200">Farmer Selling Advisory</h3>
                    </>
                  ) : (
                    <>
                      <Building className="w-5 h-5 text-teal-400" />
                      <h3 className="text-sm font-bold text-zinc-200">Trader / Policy Panel</h3>
                    </>
                  )}
                </div>

                {perspective === "farmer" ? (
                  <div className="flex flex-col gap-4 text-xs">
                    
                    {/* Recommendation Card */}
                    <div className="p-3.5 rounded-xl bg-zinc-800/50 border border-zinc-700/40">
                      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wide">Suggested Strategy</p>
                      {insights.trend === "up" ? (
                        <p className="text-emerald-400 font-bold mt-1 text-sm">Hold Crop (Price Expected to Rise)</p>
                      ) : (
                        <p className="text-rose-400 font-bold mt-1 text-sm">Sell Immediately (Prevent Losses)</p>
                      )}
                      <p className="text-zinc-400 mt-1.5 leading-relaxed">
                        {insights.trend === "up" 
                          ? `Prices at this market are forecasted to increase by ${insights.changePct.toFixed(1)}% over the next ${horizon} days. Holding inventory might yield better returns.`
                          : `Prices are expected to decline. Selling your harvest now secures the current modal rate of ₹${history?.prices[history.prices.length - 1]?.modal_price || 0}/Qtl.`}
                      </p>
                    </div>

                    {/* Regional Prices */}
                    <div>
                      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wide mb-2">Mandi Price Summary</p>
                      <div className="flex flex-col gap-2">
                        <div className="flex justify-between items-center p-2 rounded-lg bg-zinc-800/30">
                          <span className="text-zinc-350">State</span>
                          <span className="font-bold text-zinc-250">{stateName}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 rounded-lg bg-zinc-800/30">
                          <span className="text-zinc-350">District</span>
                          <span className="font-bold text-zinc-250">{districtName}</span>
                        </div>
                        <div className="flex justify-between items-center p-2 rounded-lg bg-zinc-800/30">
                          <span className="text-zinc-350">Active Mandi</span>
                          <span className="font-bold text-zinc-250">{forecast?.mandi || "Salem"}</span>
                        </div>
                      </div>
                    </div>

                  </div>
                ) : (
                  <div className="flex flex-col gap-4 text-xs">
                    
                    {/* Procurement Cost Analysis */}
                    <div className="p-3.5 rounded-xl bg-zinc-800/50 border border-zinc-700/40">
                      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wide">Procurement Advisory</p>
                      <p className="text-teal-400 font-bold mt-1 text-sm">
                        {insights.trend === "up" ? "Lock Futures Contracts" : "Procure Spot Market"}
                      </p>
                      <p className="text-zinc-400 mt-1.5 leading-relaxed">
                        {insights.trend === "up"
                          ? `With a ${insights.changePct.toFixed(1)}% upward trend forecast, locking in purchase agreements at today's rates avoids future cost inflation.`
                          : `Prices are trending down. Spot buying matches daily demand cycles best without locking high contract rates.`}
                      </p>
                    </div>

                    {/* Weather Impact Score */}
                    <div className="flex flex-col gap-2">
                      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wide">Supply Chain Yield Risk</p>
                      <div className="p-3 rounded-lg bg-zinc-800/30 border border-zinc-700/30 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CloudRain className="w-4 h-4 text-sky-400" />
                          <span className="text-zinc-350">Rainfall Disruption</span>
                        </div>
                        <span className="font-bold text-zinc-250">Minimal</span>
                      </div>
                      <div className="p-3 rounded-lg bg-zinc-800/30 border border-zinc-700/30 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Thermometer className="w-4 h-4 text-amber-500" />
                          <span className="text-zinc-350">Heat Stress Risk</span>
                        </div>
                        <span className="font-bold text-zinc-250">Low</span>
                      </div>
                    </div>

                  </div>
                )}
              </div>

              {/* Saved Queries / Search History */}
              {savedQueries.length > 0 && (
                <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                  <div className="flex items-center gap-2 pb-3 border-b border-zinc-800">
                    <span className="w-2.5 h-2.5 rounded-full bg-teal-400"></span>
                    <h3 className="text-sm font-bold text-zinc-200">Your Search History</h3>
                  </div>
                  <div className="flex flex-col gap-2 max-h-[220px] overflow-y-auto pr-1">
                    {savedQueries.map((q) => {
                      const commLabel = commodities.find(c => c.slug === q.commodity_slug)?.name || q.commodity_slug;
                      return (
                        <button
                          key={q.id}
                          onClick={() => {
                            // Check if this was a custom query
                            const isSeededComm = commodities.some(c => c.slug === q.commodity_slug);
                            const isSeededMandi = mandis.some(m => m.name === q.mandi_name);
                            if (isSeededComm && isSeededMandi) {
                              setUseCustom(false);
                              setSelectedCommodity(q.commodity_slug);
                              setSelectedMandi(q.mandi_name);
                            } else {
                              setUseCustom(true);
                              setCustomCommodity(commLabel);
                              setCustomMandi(q.mandi_name);
                              setStateName(q.state);
                              setDistrictName(q.district);
                              setStartDate(q.start_date);
                              setEndDate(q.end_date);
                            }
                          }}
                          className="w-full text-left p-2.5 rounded-lg bg-zinc-800/30 hover:bg-zinc-800/60 border border-zinc-700/20 hover:border-emerald-500/30 transition-all text-xs flex flex-col gap-1 cursor-pointer"
                        >
                          <div className="flex justify-between items-center w-full">
                            <span className="font-bold text-emerald-400 capitalize">{commLabel}</span>
                            <span className="text-[9px] text-zinc-500">{q.mandi_name} ({q.district})</span>
                          </div>
                          <div className="text-[10px] text-zinc-400 flex justify-between w-full">
                            <span>Range: {q.start_date} to {q.end_date}</span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* AI Chat Advisor */}
              <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                <div className="flex items-center gap-2 pb-3 border-b border-zinc-800">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <h3 className="text-sm font-bold text-zinc-200">AI Agricultural Co-Pilot</h3>
                </div>
                
                <div className="flex flex-col gap-3">
                  <p className="text-[10px] text-zinc-500 leading-relaxed">
                    Ask dynamic questions about pricing forecasts, monsoon impact, or market trends based on current observations.
                  </p>
                  
                  {chatReply && (
                    <div className="p-3.5 rounded-xl bg-emerald-950/10 border border-emerald-500/20 text-xs text-zinc-300 leading-relaxed whitespace-pre-line">
                      <p className="font-bold text-emerald-400 mb-1">AI Advisor:</p>
                      {chatReply}
                    </div>
                  )}

                  {chatError && (
                    <div className="p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                      {chatError}
                    </div>
                  )}
                  
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Ask the advisor..."
                      value={chatQuery}
                      onChange={(e) => setChatQuery(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && submitChat()}
                      className="flex-1 bg-zinc-805 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-emerald-500"
                    />
                    <button
                      onClick={submitChat}
                      disabled={chatLoading || !chatQuery.trim()}
                      className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-800 text-zinc-950 disabled:text-zinc-500 font-bold px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer"
                    >
                      {chatLoading ? "Thinking..." : "Ask"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Accuracy Chart */}
              <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 backdrop-blur-sm flex flex-col gap-4">
                <div>
                  <h3 className="text-sm font-bold text-zinc-200">Retrospective Live Accuracy</h3>
                  <p className="text-xs text-zinc-500">Track mean absolute error (MAE) of forecasts over past 30 days</p>
                </div>
                {accuracy.length === 0 ? (
                  <p className="text-xs text-zinc-500 text-center py-4">No live accuracy records compiled yet.</p>
                ) : (
                  <div className="h-[150px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={accuracy} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                        <XAxis dataKey="eval_date" stroke="#71717a" fontSize={8} tickLine={false} />
                        <YAxis stroke="#71717a" fontSize={8} tickLine={false} label={{ value: "MAE (₹)", angle: -90, position: "insideLeft", style: { fontSize: "8px" } }} />
                        <Tooltip contentStyle={{ backgroundColor: "#18181b", borderColor: "#3f3f46", borderRadius: "8px" }} />
                        <Line type="monotone" dataKey="mae" stroke="#10b981" strokeWidth={1.5} dot={false} name="MAE (₹)" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>

            </div>

          </div>
        )}

      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800/80 bg-zinc-950 py-6 text-center text-xs text-zinc-600">
        <p>© 2026 AgroPredict. Dynamic cross-mandi geocoding and covariate forecasting active.</p>
      </footer>
    </div>
  );
}
