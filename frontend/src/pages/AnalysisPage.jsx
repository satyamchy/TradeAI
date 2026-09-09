import { useState, useEffect, useCallback } from 'react';
import {
  fetchTodaysAnalysis,
  fetchPredictionByDate,
  fetchGlobalMacro,
  runDeepAnalysis,
  logAnalysisSnapshot,
  analyzeStocks,
  fetchPerformanceHistory,
} from '../api/stockApi';

const TABS = ['⚡ Top Movers Screener', '📊 Today\'s Analysis', '🗓️ Prediction Archive', '🎯 Accuracy Tracker'];
const SENTIMENT_COLOR = { Bullish: 'badge-green', Bearish: 'badge-red', Neutral: 'badge-amber' };
const REC_COLOR       = { BUY: 'badge-green',    SELL: 'badge-red',    HOLD: 'badge-amber'    };

function AnalysisCard({ item }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className="card p-4 transition-all hover:border-orange-500/40 cursor-pointer"
      style={{ background: '#1c1815' }}
      onClick={() => setExpanded(e => !e)}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-base" style={{ color: '#f5ebe1' }}>{item.symbol || item.ticker}</span>
            <span className="text-[11px] px-2 py-0.5 rounded font-mono" style={{ background: '#12100e', color: '#ffaa00' }}>
              {item.analysis_date || item.trade_mode || 'ANALYSIS'}
            </span>
          </div>
          <div className="text-xs mt-0.5" style={{ color: '#a89b8c' }}>{item.name || item.ticker}</div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${REC_COLOR[item.recommendation] || 'badge-amber'}`}>
            {item.recommendation}
          </span>
          <span className={`px-2 py-0.5 rounded-full text-xs ${SENTIMENT_COLOR[item.overall_sentiment] || 'badge-amber'}`}>
            {item.overall_sentiment}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
        {[
          ['Entry Price', item.initial_price ? `₹${item.initial_price.toLocaleString('en-IN')}` : '—'],
          ['Target',      item.target_price  ? `₹${item.target_price.toLocaleString('en-IN')}`  : '—'],
          ['Stop Loss',   item.stop_loss     ? `₹${item.stop_loss.toLocaleString('en-IN')}`     : '—'],
          ['Tech Score',  item.technical_score != null ? `${item.technical_score}/100` : '—'],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg p-2 text-center" style={{ background: '#12100e', border: '1px solid #2e251e' }}>
            <div className="text-[10px]" style={{ color: '#a89b8c' }}>{label}</div>
            <div className="font-semibold text-xs" style={{ color: '#f5ebe1' }}>{val}</div>
          </div>
        ))}
      </div>

      {expanded && (item.ai_reasoning || item.summary) && (
        <div className="mt-3 rounded-lg p-3 text-xs border" style={{ background: '#12100e', borderColor: '#382e26', color: '#a89b8c', lineHeight: '1.6' }}>
          <div className="text-xs font-bold mb-1 flex items-center gap-1" style={{ color: '#ff8533' }}>
            🤖 AI Rationale &amp; Key Signals
          </div>
          <p>{item.ai_reasoning || item.summary}</p>
          {item.key_signals && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.key_signals.map((sig, sIdx) => (
                <span key={sIdx} className="px-2 py-0.5 rounded text-[10px] badge-beige">{sig}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AnalysisPage() {
  const [tab, setTab] = useState(0);
  const [todayData, setTodayData] = useState([]);
  const [macroNews, setMacroNews] = useState([]);
  const [topMovers, setTopMovers] = useState([]);
  const [predDate, setPredDate] = useState(new Date().toISOString().slice(0, 10));
  const [predTicker, setPredTicker] = useState('');
  const [predData, setPredData] = useState([]);
  const [perfTicker, setPerfTicker] = useState('RELIANCE.NS');
  const [perfResult, setPerfResult] = useState(null);
  const [analyseTicker, setAnalyseTicker] = useState('');
  const [tradeMode, setTradeMode] = useState('INTRADAY');
  const [loading, setLoading] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [toast, setToast] = useState('');

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3000); };

  const loadToday = useCallback(async () => {
    setLoading(true);
    try {
      const [t, m] = await Promise.all([fetchTodaysAnalysis(), fetchGlobalMacro()]);
      setTodayData(t.results || []);
      setMacroNews(m || []);
    } catch (e) {
      showToast('Failed to load analysis snapshot data.');
    }
    setLoading(false);
  }, []);

  const loadTopMovers = async () => {
    setLoading(true);
    try {
      const res = await analyzeStocks({ mode: 'top_movers', top_n: 6, analysis_type: tradeMode.toLowerCase() });
      setTopMovers(res || []);
    } catch (err) {
      showToast('Failed to scan top movers.');
    }
    setLoading(false);
  };

  useEffect(() => {
    if (tab === 0) loadTopMovers();
    if (tab === 1) loadToday();
  }, [tab, loadToday]);

  const loadPrediction = async () => {
    if (!predDate) return;
    setLoading(true);
    try {
      const res = await fetchPredictionByDate(predDate, predTicker || undefined);
      setPredData(res.results || []);
    } catch (_) {
      showToast('Failed to fetch predictions.');
    }
    setLoading(false);
  };

  const loadPerformance = async () => {
    if (!perfTicker.trim()) return;
    setLoading(true);
    try {
      const res = await fetchPerformanceHistory(perfTicker.trim());
      setPerfResult(res);
    } catch (_) {
      showToast('No history found for ticker.');
    }
    setLoading(false);
  };

  const runAnalysis = async () => {
    if (!analyseTicker.trim()) return showToast('Enter a ticker symbol first');
    setAnalysing(true);
    try {
      const res = await runDeepAnalysis(analyseTicker.trim(), predDate, tradeMode);
      await logAnalysisSnapshot(res);
      showToast(`✅ Analysis for ${analyseTicker.toUpperCase()} logged!`);
      if (tab === 1) loadToday();
      else if (tab === 2) loadPrediction();
    } catch (_) {
      showToast('Deep analysis execution failed.');
    }
    setAnalysing(false);
  };

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      {toast && (
        <div className="fixed top-20 right-4 z-50 px-4 py-2.5 rounded-lg text-xs font-semibold shadow-2xl border"
             style={{ background: '#1c1815', borderColor: '#ff6b00', color: '#f5ebe1' }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2" style={{ color: '#f5ebe1' }}>
            <span>📊 Stock Screener &amp; AI Analysis Engine</span>
          </h1>
          <p className="text-xs" style={{ color: '#a89b8c' }}>
            Live quantitative screening, historical predictions, and accuracy benchmarks
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={tradeMode}
            onChange={e => setTradeMode(e.target.value)}
            className="rounded-lg px-2.5 py-1.5 text-xs font-semibold outline-none border"
            style={{ background: '#1c1815', borderColor: '#382e26', color: '#ffaa00' }}
          >
            <option value="INTRADAY">Mode: INTRADAY</option>
            <option value="DELIVERY">Mode: DELIVERY</option>
          </select>
          <button
            onClick={() => { if (tab === 0) loadTopMovers(); else if (tab === 1) loadToday(); }}
            className="px-3 py-1.5 rounded-lg text-xs border transition-all hover:border-orange-500/40"
            style={{ borderColor: '#382e26', color: '#a89b8c' }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex gap-2 border-b overflow-x-auto pb-1" style={{ borderColor: '#382e26' }}>
        {TABS.map((t, i) => (
          <button
            key={i}
            onClick={() => setTab(i)}
            className={`pb-2 px-3 text-xs font-bold border-b-2 transition-all whitespace-nowrap ${
              tab === i ? 'border-orange-500 text-orange-400' : 'border-transparent text-stone-500 hover:text-stone-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Toolbar for On-Demand Analysis */}
      <div className="card p-3 flex flex-wrap gap-2 items-center" style={{ background: '#1c1815' }}>
        <input
          value={analyseTicker}
          onChange={e => setAnalyseTicker(e.target.value)}
          placeholder="Analyze specific stock (e.g. RELIANCE.NS, TCS, INFY)"
          className="flex-1 min-w-[200px] rounded-lg px-3 py-2 text-xs outline-none"
          style={{ background: '#12100e', border: '1px solid #382e26', color: '#f5ebe1' }}
        />
        <button
          onClick={runAnalysis}
          disabled={analysing}
          className="px-4 py-2 rounded-lg text-xs font-bold text-white transition-all hover:opacity-90 disabled:opacity-50"
          style={{ background: 'linear-gradient(135deg, #ff6b00, #e65100)' }}
        >
          {analysing ? 'Evaluating…' : '⚡ Run Deep Analysis'}
        </button>
      </div>

      {/* Tab 0: Top Movers Screener */}
      {tab === 0 && (
        <div className="space-y-4">
          {loading ? (
            <div className="card p-8 text-center text-xs" style={{ color: '#a89b8c' }}>Scanning Indian stock market top movers…</div>
          ) : topMovers.length === 0 ? (
            <div className="card p-8 text-center text-xs" style={{ color: '#a89b8c' }}>No top movers loaded. Click refresh to scan.</div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {topMovers.map((item, idx) => <AnalysisCard key={idx} item={item} />)}
            </div>
          )}
        </div>
      )}

      {/* Tab 1: Today's Analysis & Global Macro */}
      {tab === 1 && (
        <div className="space-y-4">
          {loading ? (
            <div className="card p-8 text-center text-xs" style={{ color: '#a89b8c' }}>Loading today's snapshots…</div>
          ) : todayData.length === 0 ? (
            <div className="card p-8 text-center text-xs" style={{ color: '#a89b8c' }}>
              No analysis records stored for today. Run an analysis above.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {todayData.map(item => <AnalysisCard key={item.id} item={item} />)}
            </div>
          )}

          {/* Macro News Feed */}
          {macroNews.length > 0 && (
            <div className="card p-4 space-y-3" style={{ background: '#1c1815' }}>
              <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#ffaa00' }}>
                🌍 Domestic &amp; Global Macro Pulse
              </h2>
              <div className="grid gap-2 sm:grid-cols-2">
                {macroNews.map((m, mIdx) => (
                  <div key={mIdx} className="p-3 rounded-lg border text-xs" style={{ background: '#12100e', borderColor: '#2e251e' }}>
                    <div className="flex justify-between items-start gap-2">
                      <span className="font-semibold text-stone-200">{m.title}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${SENTIMENT_COLOR[m.sentiment] || 'badge-amber'}`}>
                        {m.sentiment}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px]" style={{ color: '#a89b8c' }}>{m.summary}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Prediction by Date */}
      {tab === 2 && (
        <div className="space-y-4">
          <div className="card p-3 flex flex-wrap gap-2 items-end" style={{ background: '#1c1815' }}>
            <div className="flex flex-col gap-1">
              <label className="text-[11px]" style={{ color: '#a89b8c' }}>Select Date</label>
              <input
                type="date"
                value={predDate}
                onChange={e => setPredDate(e.target.value)}
                className="rounded-lg px-2.5 py-1.5 text-xs outline-none"
                style={{ background: '#12100e', border: '1px solid #382e26', color: '#f5ebe1' }}
              />
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-[150px]">
              <label className="text-[11px]" style={{ color: '#a89b8c' }}>Ticker (optional)</label>
              <input
                value={predTicker}
                onChange={e => setPredTicker(e.target.value)}
                placeholder="e.g. RELIANCE.NS"
                className="rounded-lg px-2.5 py-1.5 text-xs outline-none"
                style={{ background: '#12100e', border: '1px solid #382e26', color: '#f5ebe1' }}
              />
            </div>
            <button
              onClick={loadPrediction}
              className="px-4 py-2 rounded-lg text-xs font-bold text-white"
              style={{ background: '#ff6b00' }}
            >
              Search Archive
            </button>
          </div>

          {predData.length === 0 ? (
            <div className="card p-8 text-center text-xs" style={{ color: '#a89b8c' }}>
              No prediction snapshots found for date {predDate}.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {predData.map(item => <AnalysisCard key={item.id} item={item} />)}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Accuracy Tracker */}
      {tab === 3 && (
        <div className="space-y-4">
          <div className="card p-3 flex flex-wrap gap-2 items-center" style={{ background: '#1c1815' }}>
            <input
              value={perfTicker}
              onChange={e => setPerfTicker(e.target.value)}
              placeholder="Enter ticker (e.g. RELIANCE.NS)"
              className="flex-1 rounded-lg px-3 py-2 text-xs outline-none"
              style={{ background: '#12100e', border: '1px solid #382e26', color: '#f5ebe1' }}
            />
            <button
              onClick={loadPerformance}
              className="px-4 py-2 rounded-lg text-xs font-bold text-white"
              style={{ background: '#ff6b00' }}
            >
              Audit Accuracy
            </button>
          </div>

          {perfResult && (
            <div className="card p-4 space-y-4" style={{ background: '#1c1815' }}>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg text-center" style={{ background: '#12100e' }}>
                  <div className="text-[10px]" style={{ color: '#a89b8c' }}>Overall Accuracy</div>
                  <div className="text-xl font-bold" style={{ color: '#10b981' }}>
                    {perfResult.overall_ai_accuracy_score_pct ?? '—'}%
                  </div>
                </div>
                <div className="p-3 rounded-lg text-center" style={{ background: '#12100e' }}>
                  <div className="text-[10px]" style={{ color: '#a89b8c' }}>Trust Rating</div>
                  <div className="text-sm font-bold" style={{ color: '#ffaa00' }}>
                    {perfResult.trust_rating ?? 'Evaluating'}
                  </div>
                </div>
                <div className="p-3 rounded-lg text-center" style={{ background: '#12100e' }}>
                  <div className="text-[10px]" style={{ color: '#a89b8c' }}>Total Snapshots</div>
                  <div className="text-sm font-bold" style={{ color: '#f5ebe1' }}>
                    {perfResult.total_snapshots ?? 0}
                  </div>
                </div>
                <div className="p-3 rounded-lg text-center" style={{ background: '#12100e' }}>
                  <div className="text-[10px]" style={{ color: '#a89b8c' }}>Live Market Price</div>
                  <div className="text-sm font-bold" style={{ color: '#ff8533' }}>
                    ₹{perfResult.live_current_price ?? '—'}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
