import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// ── Conversational AI Agent ───────────────────────────────────────────────────
export const processConversation = (query, ticker) =>
  api.post('/api/conversation', { query, ticker }).then(r => r.data);

// ── Market ────────────────────────────────────────────────────────────────────
export const fetchMarketStatus  = () => api.get('/v1/market/status').then(r => r.data);
export const fetchMarketIndices = () => api.get('/v1/market/indices').then(r => r.data);

// ── Data & AI Analysis ────────────────────────────────────────────────────────
export const fetchGlobalMacro      = ()                          => api.get('/v1/data/global-macro').then(r => r.data);
export const fetchIntervalData     = (ticker, timeframe = '15m') => api.get(`/v1/data/interval-data/${ticker}`, { params: { timeframe } }).then(r => r.data);
export const runDeepAnalysis       = (ticker, date_str, trade_mode = 'INTRADAY') => api.post('/v1/data/deep-analysis', null, { params: { ticker, date_str, trade_mode } }).then(r => r.data);
export const fetchPositionMonitor  = ()                          => api.get('/v1/data/position-monitor').then(r => r.data);

// ── Stock Screener & Batch Analysis ───────────────────────────────────────────
export const analyzeStocks = (payload) => api.post('/api/v1/stocks/analyze', payload).then(r => r.data);

// ── Analysis Snapshots & History ──────────────────────────────────────────────
export const fetchTodaysAnalysis   = (ticker)        => api.get('/v1/analysis/today', { params: ticker ? { ticker } : {} }).then(r => r.data);
export const fetchPredictionByDate = (date, ticker)  => api.get('/v1/analysis/prediction', { params: ticker ? { date, ticker } : { date } }).then(r => r.data);
export const logAnalysisSnapshot   = (payload)       => api.post('/v1/analysis/log', payload).then(r => r.data);
export const fetchPerformanceHistory = (ticker)      => api.get(`/v1/snapshots/${ticker}/performance`).then(r => r.data);

// ── Trades & Journal ──────────────────────────────────────────────────────────
export const fetchTrades       = (params)   => api.get('/v1/trades/', { params }).then(r => r.data);
export const createTrade       = (payload)  => api.post('/v1/trades/', payload).then(r => r.data);
export const updateTrade       = (id, data) => api.put(`/v1/trades/${id}`, data).then(r => r.data);
export const deleteTrade       = (id)       => api.delete(`/v1/trades/${id}`).then(r => r.data);
export const fetchTradeSummary = ()         => api.get('/v1/trades/summary').then(r => r.data);

// ── Trading & Guardrails (DhanHQ / Paper) ─────────────────────────────────────
export const fetchGuardrailStatus = ()         => api.get('/v1/trading/guardrails/status').then(r => r.data);
export const toggleTrading        = (enabled)  => api.post('/v1/trading/guardrails/toggle', { is_trading_enabled: enabled }).then(r => r.data);
export const placeOrder           = (payload)  => api.post('/v1/trading/orders', payload).then(r => r.data);
export const squareOffPosition    = (id, data) => api.post(`/v1/trading/square-off/${id}`, data).then(r => r.data);

// ── Scheduled Jobs & Cron ─────────────────────────────────────────────────────
export const fetchJobs    = ()        => api.get('/v1/jobs/').then(r => r.data);
export const createJob    = (payload) => api.post('/v1/jobs/', payload).then(r => r.data);
export const triggerJob   = (id)      => api.post(`/v1/jobs/${id}/run`).then(r => r.data);
export const deleteJob    = (id)      => api.delete(`/v1/jobs/${id}`).then(r => r.data);
export const fetchJobLogs = (job_id)  => api.get('/v1/jobs/logs', { params: job_id ? { job_id } : {} }).then(r => r.data);

export default api;
