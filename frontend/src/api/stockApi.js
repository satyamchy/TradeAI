import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/v1';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// ── Market ────────────────────────────────────────────────────────────────────
export const fetchMarketStatus  = ()           => api.get('/market/status').then(r => r.data);
export const fetchMarketIndices = ()           => api.get('/market/indices').then(r => r.data);

// ── Data & AI Analysis ────────────────────────────────────────────────────────
export const fetchGlobalMacro      = ()                            => api.get('/data/global-macro').then(r => r.data);
export const fetchIntervalData     = (ticker, timeframe = '15m')   => api.get(`/data/interval-data/${ticker}`, { params: { timeframe } }).then(r => r.data);
export const runDeepAnalysis       = (ticker, date_str)             => api.post('/data/deep-analysis', null, { params: { ticker, date_str } }).then(r => r.data);
export const fetchPositionMonitor  = ()                            => api.get('/data/position-monitor').then(r => r.data);

// ── Analysis Logs ─────────────────────────────────────────────────────────────
export const fetchTodaysAnalysis   = (ticker)   => api.get('/analysis/today',      { params: ticker ? { ticker } : {} }).then(r => r.data);
export const fetchPredictionByDate = (date, ticker) => api.get('/analysis/prediction', { params: ticker ? { date, ticker } : { date } }).then(r => r.data);
export const logAnalysisSnapshot   = (payload)  => api.post('/analysis/log', payload).then(r => r.data);

// ── Trades ────────────────────────────────────────────────────────────────────
export const fetchTrades      = (params)    => api.get('/trades/',          { params }).then(r => r.data);
export const createTrade      = (payload)   => api.post('/trades/',          payload).then(r => r.data);
export const updateTrade      = (id, data)  => api.put(`/trades/${id}`,      data).then(r => r.data);
export const deleteTrade      = (id)        => api.delete(`/trades/${id}`).then(r => r.data);
export const fetchTradeSummary= ()          => api.get('/trades/summary').then(r => r.data);

// ── Trading (DhanHQ) ─────────────────────────────────────────────────────────
export const fetchGuardrailStatus = ()             => api.get('/trading/guardrails/status').then(r => r.data);
export const toggleTrading        = (enabled)      => api.post('/trading/guardrails/toggle', { is_trading_enabled: enabled }).then(r => r.data);
export const placeOrder           = (payload)      => api.post('/trading/orders',   payload).then(r => r.data);
export const squareOffPosition    = (id, data)     => api.post(`/trading/square-off/${id}`, data).then(r => r.data);

// ── Jobs ──────────────────────────────────────────────────────────────────────
export const fetchJobs      = ()          => api.get('/jobs/').then(r => r.data);
export const createJob      = (payload)   => api.post('/jobs/',           payload).then(r => r.data);
export const triggerJob     = (id)        => api.post(`/jobs/${id}/run`).then(r => r.data);
export const deleteJob      = (id)        => api.delete(`/jobs/${id}`).then(r => r.data);
export const fetchJobLogs   = (job_id)    => api.get('/jobs/logs', { params: job_id ? { job_id } : {} }).then(r => r.data);

export default api;
