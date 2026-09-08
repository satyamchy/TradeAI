import { useState, useEffect, useCallback } from 'react';
import {
  fetchTodaysAnalysis,
  fetchPredictionByDate,
  fetchGlobalMacro,
  runDeepAnalysis,
  logAnalysisSnapshot,
} from '../api/stockApi';

const TABS = ['Today\'s Analysis', 'Prediction by Date'];
const SENTIMENT_COLOR = { Bullish: 'badge-green', Bearish: 'badge-red', Neutral: 'badge-amber' };
const REC_COLOR       = { BUY: 'badge-green',    SELL: 'badge-red',    HOLD: 'badge-amber'    };

// ── Reusable Analysis Card ────────────────────────────────────────────────────
function AnalysisCard({ item }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="card p-4 transition-all hover:border-blue-500/30 cursor-pointer" onClick={() => setExpanded(e => !e)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        {/* Symbol + Date */}
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-base" style={{ color: '#e8f0fe' }}>{item.symbol}</span>
            <span className="text-xs px-2 py-0.5 rounded" style={{ background: '#1a2d4a', color: '#8899b3' }}>
              {item.analysis_date}
            </span>
          </div>
          <div className="text-xs mt-0.5" style={{ color: '#8899b3' }}>{item.name || item.ticker}</div>
        </div>

        {/* Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${REC_COLOR[item.recommendation] || 'badge-amber'}`}>
            {item.recommendation}
          </span>
          <span className={`px-2 py-0.5 rounded-full text-xs ${SENTIMENT_COLOR[item.overall_sentiment] || 'badge-amber'}`}>
            {item.overall_sentiment}
          </span>
        </div>
      </div>

      {/* Price strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
        {[
          ['Entry Price',  item.initial_price ? `₹${item.initial_price.toLocaleString('en-IN')}` : '—'],
          ['Target',       item.target_price  ? `₹${item.target_price.toLocaleString('en-IN')}`  : '—'],
          ['Stop Loss',    item.stop_loss     ? `₹${item.stop_loss.toLocaleString('en-IN')}`     : '—'],
          ['Tech Score',   item.technical_score != null ? `${item.technical_score}/100` : '—'],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg p-2 text-center" style={{ background: '#060b14' }}>
            <div className="text-xs" style={{ color: '#8899b3' }}>{label}</div>
            <div className="font-semibold text-sm" style={{ color: '#e8f0fe' }}>{val}</div>
          </div>
        ))}
      </div>

      {/* AI Reasoning (expandable) */}
      {expanded && item.ai_reasoning && (
        <div className="mt-3 rounded-lg p-3 text-xs" style={{ background: '#060b14', color: '#8899b3', lineHeight: '1.6' }}>
          <div className="text-xs font-semibold mb-1" style={{ color: '#2979ff' }}>🤖 AI Reasoning</div>
          {item.ai_reasoning}
        </div>
      )}
    </div>
  );
}

// ── Macro News Card ───────────────────────────────────────────────────────────
function MacroCard({ item }) {
  const color = item.sentiment === 'Positive' ? '#00e676' : item.sentiment === 'Negative' ? '#ff1744' : '#ffc107';
  const bg    = item.sentiment === 'Positive' ? 'rgba(0,230,118,0.08)' : item.sentiment === 'Negative' ? 'rgba(255,23,68,0.08)' : 'rgba(255,193,7,0.08)';
  return (
    <div className="rounded-lg p-3 border" style={{ background: bg, borderColor: `${color}33` }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="text-xs font-semibold leading-snug" style={{ color: '#e8f0fe' }}>{item.title}</div>
          <div className="text-xs mt-1" style={{ color: '#8899b3' }}>{item.summary}</div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ color, background: bg, border: `1px solid ${color}44` }}>
            {item.sentiment}
          </span>
          <span className="text-xs font-mono" style={{ color }}>
            Impact: {item.impact_score > 0 ? '+' : ''}{item.impact_score}
          </span>
        </div>
      </div>
      <div className="text-xs mt-1 flex gap-2" style={{ color: '#8899b3' }}>
        <span>{item.region}</span> · <span>{item.published_at}</span>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function AnalysisPage() {
  const [tab,          setTab]          = useState(0);
  const [todayData,    setTodayData]    = useState([]);
  const [macroNews,    setMacroNews]    = useState([]);
  const [predDate,     setPredDate]     = useState(new Date().toISOString().slice(0, 10));
  const [predTicker,   setPredTicker]   = useState('');
  const [predData,     setPredData]     = useState([]);
  const [analyseTicker,setAnalyseTicker]= useState('');
  const [loading,      setLoading]      = useState(false);
  const [analysing,    setAnalysing]    = useState(false);
  const [toast,        setToast]        = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  // Load today's data
  const loadToday = useCallback(async () => {
    setLoading(true);
    try {
      const [t, m] = await Promise.all([fetchTodaysAnalysis(), fetchGlobalMacro()]);
      setTodayData(t.results || []);
      setMacroNews(m);
    } catch (e) {
      showToast('Failed to load today\'s data');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadToday(); }, [loadToday]);

  // Load prediction by date
  const loadPrediction = async () => {
    if (!predDate) return;
    setLoading(true);
    try {
      const res = await fetchPredictionByDate(predDate, predTicker || undefined);
      setPredData(res.results || []);
    } catch (_) { showToast('Failed to fetch predictions'); }
    setLoading(false);
  };

  // Run deep AI analysis and log it
  const runAnalysis = async () => {
    if (!analyseTicker.trim()) return showToast('Enter a ticker symbol first');
    setAnalysing(true);
    try {
      const res = await runDeepAnalysis(analyseTicker.trim(), predDate);
      await logAnalysisSnapshot(res);
      showToast(`✅ Analysis for ${analyseTicker.toUpperCase()} logged!`);
      if (tab === 1) loadPrediction();
      else loadToday();
    } catch (_) { showToast('Analysis failed'); }
    setAnalysing(false);
  };

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      {/* Toast */}
      {toast && (
        <div className="fixed top-20 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium shadow-xl"
             style={{ background: '#0c1526', border: '1px solid #2979ff', color: '#e8f0fe' }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#e8f0fe' }}>📊 Stock Analysis & AI Predictions</h1>
          <p className="text-xs mt-0.5" style={{ color: '#8899b3' }}>
            NSE/BSE deep analysis powered by AI agents · Indian market timeframe
          </p>
        </div>
        <button onClick={loadToday} className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:bg-blue-500/10"
                style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>
          ↻ Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b" style={{ borderColor: '#1a2d4a' }}>
        {TABS.map((t, i) => (
          <button key={i} onClick={() => setTab(i)}
            className={`pb-2 px-3 text-sm font-medium border-b-2 transition-all ${
              tab === i ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}>
            {t}
          </button>
        ))}
      </div>

      {/* ── Tab 1: Today's Analysis ─────────────────────────────────────── */}
      {tab === 0 && (
        <div className="space-y-4">
          {/* Run analysis toolbar */}
          <div className="card p-3 flex flex-wrap gap-2 items-center">
            <input
              value={analyseTicker} onChange={e => setAnalyseTicker(e.target.value)}
              placeholder="e.g. RELIANCE.NS or TCS.NS"
              className="flex-1 min-w-0 rounded-lg px-3 py-2 text-sm outline-none"
              style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
            />
            <button
              onClick={runAnalysis} disabled={analysing}
              className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg,#2979ff,#7c4dff)' }}>
              {analysing ? 'Analysing…' : '🤖 Run AI Analysis'}
            </button>
          </div>

          {loading ? (
            <div className="text-center py-12 text-sm" style={{ color: '#8899b3' }}>Loading today's data…</div>
          ) : todayData.length === 0 ? (
            <div className="card p-8 text-center space-y-2">
              <div className="text-4xl">📈</div>
              <p className="text-sm font-medium" style={{ color: '#e8f0fe' }}>No analysis snapshots for today yet.</p>
              <p className="text-xs" style={{ color: '#8899b3' }}>Use the toolbar above to run AI analysis for any ticker.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {todayData.map(item => <AnalysisCard key={item.id} item={item} />)}
            </div>
          )}

          {/* Global Macro News */}
          <div>
            <h2 className="text-sm font-bold mb-2" style={{ color: '#e8f0fe' }}>🌍 Global Macro &amp; World Events</h2>
            <div className="space-y-2">
              {macroNews.map((item, i) => <MacroCard key={i} item={item} />)}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab 2: Prediction by Date ──────────────────────────────────── */}
      {tab === 1 && (
        <div className="space-y-4">
          {/* Date + Ticker filter */}
          <div className="card p-3 flex flex-wrap gap-3 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: '#8899b3' }}>Select Date</label>
              <input type="date" value={predDate} onChange={e => setPredDate(e.target.value)}
                className="rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
              />
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-0">
              <label className="text-xs" style={{ color: '#8899b3' }}>Ticker (optional)</label>
              <input
                value={predTicker} onChange={e => setPredTicker(e.target.value)}
                placeholder="e.g. RELIANCE.NS"
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
              />
            </div>
            <button onClick={loadPrediction} className="px-4 py-2 rounded-lg text-sm font-semibold text-white"
                    style={{ background: '#2979ff' }}>
              🔍 Fetch Predictions
            </button>
            <button onClick={runAnalysis} disabled={analysing}
                    className="px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
                    style={{ background: 'linear-gradient(135deg,#7c4dff,#2979ff)' }}>
              {analysing ? 'Running…' : '🤖 Generate & Log'}
            </button>
          </div>

          {loading ? (
            <div className="text-center py-12 text-sm" style={{ color: '#8899b3' }}>Fetching predictions…</div>
          ) : predData.length === 0 ? (
            <div className="card p-8 text-center space-y-2">
              <div className="text-4xl">🗓️</div>
              <p className="text-sm font-medium" style={{ color: '#e8f0fe' }}>No predictions found for {predDate}.</p>
              <p className="text-xs" style={{ color: '#8899b3' }}>Enter a ticker and click "Generate & Log" to create one.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {predData.map(item => <AnalysisCard key={item.id} item={item} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
