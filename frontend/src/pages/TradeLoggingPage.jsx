import { useState, useEffect, useCallback } from 'react';
import {
  fetchTrades, createTrade, updateTrade, deleteTrade, fetchTradeSummary,
  fetchPositionMonitor, placeOrder, squareOffPosition, fetchGuardrailStatus,
} from '../api/stockApi';

const PROD_TYPES   = ['INTRADAY', 'DELIVERY'];
const ASSET_CATS   = ['STOCK', 'GOLD', 'SILVER'];
const TRADE_TYPES  = ['BUY', 'SELL'];

const emptyForm = {
  trade_date: new Date().toISOString().slice(0, 10),
  trade_time: '',
  symbol: '',
  trade_type: 'BUY',
  product_type: 'INTRADAY',
  asset_category: 'STOCK',
  quantity: '',
  price: '',
  stop_loss: '',
  target_price: '',
  brokerage: '',
  notes: '',
};

// ── Summary Card ──────────────────────────────────────────────────────────────
function SummaryCard({ label, value, sub, color }) {
  return (
    <div className="card p-4">
      <div className="text-xs mb-1" style={{ color: '#8899b3' }}>{label}</div>
      <div className={`text-xl font-bold ${color || ''}`} style={!color ? { color: '#e8f0fe' } : {}}>
        {value}
      </div>
      {sub && <div className="text-xs mt-0.5" style={{ color: '#8899b3' }}>{sub}</div>}
    </div>
  );
}

// ── Open Position Row ─────────────────────────────────────────────────────────
function PositionRow({ pos, onSquareOff }) {
  const [exitPrice, setExitPrice] = useState('');
  const pnlColor = pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400';
  return (
    <tr className="table-row-hover border-b" style={{ borderColor: '#1a2d4a' }}>
      <td className="px-3 py-2 font-semibold text-sm" style={{ color: '#e8f0fe' }}>{pos.symbol}</td>
      <td className="px-3 py-2">
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${pos.trade_type === 'BUY' ? 'badge-green' : 'badge-red'}`}>
          {pos.trade_type}
        </span>
      </td>
      <td className="px-3 py-2 text-xs" style={{ color: '#8899b3' }}>{pos.product_type}</td>
      <td className="px-3 py-2 text-sm font-mono" style={{ color: '#e8f0fe' }}>₹{pos.entry_price}</td>
      <td className="px-3 py-2 text-sm font-mono" style={{ color: '#e8f0fe' }}>₹{pos.current_price}</td>
      <td className={`px-3 py-2 text-sm font-bold font-mono ${pnlColor}`}>
        {pos.unrealized_pnl >= 0 ? '+' : ''}₹{pos.unrealized_pnl}
      </td>
      <td className="px-3 py-2">
        {pos.needs_auto_squareoff && (
          <span className="px-2 py-0.5 rounded text-xs font-bold badge-red animate-pulse">AUTO EXIT</span>
        )}
        {pos.recommendation === 'WATCH_STOP_LOSS' && (
          <span className="px-2 py-0.5 rounded text-xs badge-amber">STOP WATCH</span>
        )}
      </td>
      <td className="px-3 py-2 flex gap-2 items-center">
        <input
          value={exitPrice} onChange={e => setExitPrice(e.target.value)}
          placeholder="Exit ₹" className="w-20 rounded px-2 py-1 text-xs outline-none"
          style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
        />
        <button
          onClick={() => onSquareOff(pos.trade_id, exitPrice)}
          className="px-2 py-1 rounded text-xs font-bold transition-all hover:opacity-90"
          style={{ background: '#ff1744', color: '#fff' }}>
          Exit
        </button>
      </td>
    </tr>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function TradeLoggingPage() {
  const [trades,      setTrades]      = useState([]);
  const [summary,     setSummary]     = useState(null);
  const [positions,   setPositions]   = useState([]);
  const [guardrails,  setGuardrails]  = useState(null);
  const [form,        setForm]        = useState(emptyForm);
  const [editId,      setEditId]      = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [showForm,    setShowForm]    = useState(false);
  const [toast,       setToast]       = useState('');
  const [filters, setFilters] = useState({
    start_date: '', end_date: '', symbol: '', trade_type: '', product_type: '', asset_category: '',
  });

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3500); };

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [t, s, p, g] = await Promise.all([
        fetchTrades(filters),
        fetchTradeSummary(),
        fetchPositionMonitor(),
        fetchGuardrailStatus(),
      ]);
      setTrades(t.trades || []);
      setSummary(s);
      setPositions(p.positions || []);
      setGuardrails(g);
    } catch (_) {}
    setLoading(false);
  }, [filters]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleFormChange = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.symbol || !form.quantity || !form.price) return showToast('Symbol, Quantity and Price are required');
    try {
      const payload = {
        ...form,
        quantity:      parseInt(form.quantity),
        price:         parseFloat(form.price),
        stop_loss:     form.stop_loss    ? parseFloat(form.stop_loss)    : null,
        target_price:  form.target_price ? parseFloat(form.target_price) : null,
        brokerage:     form.brokerage    ? parseFloat(form.brokerage)    : 0,
      };
      if (editId) {
        await updateTrade(editId, payload);
        showToast('Trade updated.');
      } else {
        await createTrade(payload);
        showToast('✅ Trade logged successfully!');
      }
      setForm(emptyForm);
      setEditId(null);
      setShowForm(false);
      loadAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Failed to save trade');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this trade?')) return;
    await deleteTrade(id);
    showToast('Trade deleted.');
    loadAll();
  };

  const handleEdit = (t) => {
    setForm({
      trade_date:    t.trade_date,
      trade_time:    t.trade_time || '',
      symbol:        t.symbol,
      trade_type:    t.trade_type,
      product_type:  t.product_type,
      asset_category:t.asset_category,
      quantity:      t.quantity,
      price:         t.price,
      stop_loss:     t.stop_loss    || '',
      target_price:  t.target_price || '',
      brokerage:     t.brokerage    || '',
      notes:         t.notes        || '',
    });
    setEditId(t.id);
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSquareOff = async (tradeId, exitPrice) => {
    if (!exitPrice) return showToast('Enter exit price');
    try {
      const res = await squareOffPosition(tradeId, { exit_price: parseFloat(exitPrice) });
      showToast(`✅ Squared off! P&L: ₹${res.realized_pnl}`);
      loadAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Square-off failed');
    }
  };

  // Guardrail check for DhanHQ order form
  const handlePlaceOrder = async () => {
    if (!guardrails?.is_trading_enabled) {
      return showToast('❌ Trading is DISABLED. Enable from the header Kill-Switch first.');
    }
    const payload = {
      ...form,
      quantity:     parseInt(form.quantity),
      price:        parseFloat(form.price),
      stop_loss:    form.stop_loss    ? parseFloat(form.stop_loss)    : null,
      target_price: form.target_price ? parseFloat(form.target_price) : null,
    };
    try {
      const res = await placeOrder(payload);
      showToast(`✅ Order placed! ID: ${res.order_id} | Mode: ${res.mode}`);
      setShowForm(false);
      setForm(emptyForm);
      loadAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Order failed');
    }
  };

  const pnlColor = summary?.realized_pnl_inr >= 0 ? 'text-green-400' : 'text-red-400';

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
          <h1 className="text-xl font-bold" style={{ color: '#e8f0fe' }}>💹 Trade Logs &amp; Orders</h1>
          <p className="text-xs mt-0.5" style={{ color: '#8899b3' }}>
            Log buy/sell for Stocks, Gold, Silver · Intraday &amp; Delivery · Powered by DhanHQ
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} className="px-3 py-1.5 rounded-lg text-xs border transition-all hover:bg-white/5"
                  style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>↻ Refresh</button>
          <button
            onClick={() => { setShowForm(f => !f); setEditId(null); setForm(emptyForm); }}
            className="px-4 py-1.5 rounded-lg text-sm font-semibold text-white"
            style={{ background: 'linear-gradient(135deg,#00e676,#00b248)', color: '#000' }}>
            + Log Trade
          </button>
        </div>
      </div>

      {/* ── Summary Cards ─────────────────────────────────────────────── */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <SummaryCard label="Total Trades"   value={summary.total_trades}
            sub={`${summary.buy_count} BUY · ${summary.sell_count} SELL`} />
          <SummaryCard label="Capital Deployed" value={`₹${(summary.total_capital_deployed_inr || 0).toLocaleString('en-IN')}`} />
          <SummaryCard label="Realized P&L"
            value={`${summary.realized_pnl_inr >= 0 ? '+' : ''}₹${(summary.realized_pnl_inr || 0).toLocaleString('en-IN')}`}
            color={pnlColor} />
          <SummaryCard label="Win Rate" value={`${summary.win_rate_pct?.toFixed(1) || 0}%`} />
        </div>
      )}

      {/* ── Open Positions Monitor ────────────────────────────────────── */}
      {positions.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: '#1a2d4a' }}>
            <span className="w-2 h-2 rounded-full bg-green-400 pulse-dot"></span>
            <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>Open Positions — Live Monitor</h2>
            <span className="text-xs px-2 py-0.5 rounded-full badge-amber">
              Intraday auto-exit before 3:15 PM IST
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#8899b3', background: '#060b14' }}>
                  {['Symbol','Type','Product','Entry','Current','Unrealized P&L','Signal','Action'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map(pos => (
                  <PositionRow key={pos.trade_id} pos={pos} onSquareOff={handleSquareOff} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Trade Form ────────────────────────────────────────────────── */}
      {showForm && (
        <div className="card p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>
              {editId ? '✏️ Edit Trade' : '➕ New Trade Log'}
            </h2>
            {!guardrails?.is_trading_enabled && (
              <span className="text-xs px-2 py-1 rounded badge-red font-bold">
                ⚠️ Live Trading OFF — Guardrails Active
              </span>
            )}
            {guardrails?.paper_trading_mode && (
              <span className="text-xs px-2 py-1 rounded badge-amber font-bold">📄 Paper Trading Mode</span>
            )}
          </div>

          <form onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {/* Trade Type toggle */}
              <div className="col-span-2 sm:col-span-3 lg:col-span-4 flex gap-2">
                {TRADE_TYPES.map(t => (
                  <button type="button" key={t} onClick={() => handleFormChange('trade_type', t)}
                    className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${
                      form.trade_type === t
                        ? t === 'BUY' ? 'badge-green' : 'badge-red'
                        : 'opacity-40 badge-blue'
                    }`}>
                    {t === 'BUY' ? '↑ BUY' : '↓ SELL'}
                  </button>
                ))}
              </div>

              {/* Inputs */}
              {[
                ['trade_date', 'Date', 'date'],
                ['trade_time', 'Time (optional)', 'time'],
                ['symbol',     'Symbol / Ticker', 'text'],
                ['quantity',   'Quantity',         'number'],
                ['price',      'Price (₹)',         'number'],
                ['stop_loss',  'Stop Loss (₹)',     'number'],
                ['target_price','Target (₹)',       'number'],
                ['brokerage',  'Brokerage (₹)',     'number'],
              ].map(([key, label, type]) => (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-xs" style={{ color: '#8899b3' }}>{label}</label>
                  <input
                    type={type} value={form[key]}
                    onChange={e => handleFormChange(key, e.target.value)}
                    placeholder={key === 'symbol' ? 'RELIANCE.NS' : ''}
                    className="rounded-lg px-3 py-2 text-sm outline-none"
                    style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
                  />
                </div>
              ))}

              {/* Product Type */}
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>Product Type</label>
                <select value={form.product_type} onChange={e => handleFormChange('product_type', e.target.value)}
                  className="rounded-lg px-3 py-2 text-sm outline-none"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}>
                  {PROD_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              {/* Asset Category */}
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>Asset Category</label>
                <select value={form.asset_category} onChange={e => handleFormChange('asset_category', e.target.value)}
                  className="rounded-lg px-3 py-2 text-sm outline-none"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}>
                  {ASSET_CATS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>

              {/* Notes */}
              <div className="col-span-2 sm:col-span-3 lg:col-span-4 flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>Notes (optional)</label>
                <input value={form.notes} onChange={e => handleFormChange('notes', e.target.value)}
                  placeholder="AI reasoning, entry rationale…"
                  className="rounded-lg px-3 py-2 text-sm outline-none w-full"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
                />
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap gap-3 mt-4">
              <button type="submit"
                className="px-5 py-2 rounded-lg text-sm font-bold text-white transition-all hover:opacity-90"
                style={{ background: 'linear-gradient(135deg,#2979ff,#7c4dff)' }}>
                {editId ? 'Update Trade' : '💾 Log Trade (Manual)'}
              </button>
              {!editId && (
                <button type="button" onClick={handlePlaceOrder}
                  className="px-5 py-2 rounded-lg text-sm font-bold transition-all hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg,#00e676,#00b248)', color: '#000' }}>
                  🚀 Execute via DhanHQ
                </button>
              )}
              <button type="button" onClick={() => { setShowForm(false); setForm(emptyForm); setEditId(null); }}
                className="px-4 py-2 rounded-lg text-sm border transition-all hover:bg-white/5"
                style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Filters ───────────────────────────────────────────────────── */}
      <div className="card p-3 flex flex-wrap gap-3 items-end">
        {[
          ['start_date', 'From Date', 'date'],
          ['end_date',   'To Date',   'date'],
          ['symbol',     'Symbol',    'text'],
        ].map(([key, label, type]) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-xs" style={{ color: '#8899b3' }}>{label}</label>
            <input type={type} value={filters[key]}
              onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}
              className="rounded-lg px-3 py-1.5 text-xs outline-none"
              style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}
            />
          </div>
        ))}
        {[
          ['trade_type',    ['','BUY','SELL']],
          ['product_type',  ['','INTRADAY','DELIVERY']],
          ['asset_category',['','STOCK','GOLD','SILVER']],
        ].map(([key, opts]) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-xs capitalize" style={{ color: '#8899b3' }}>{key.replace('_',' ')}</label>
            <select value={filters[key]} onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}
              className="rounded-lg px-3 py-1.5 text-xs outline-none"
              style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }}>
              {opts.map(o => <option key={o} value={o}>{o || 'All'}</option>)}
            </select>
          </div>
        ))}
        <button onClick={loadAll} className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white"
                style={{ background: '#2979ff' }}>Filter</button>
        <button onClick={() => { setFilters({ start_date:'',end_date:'',symbol:'',trade_type:'',product_type:'',asset_category:'' }); }}
          className="px-3 py-1.5 rounded-lg text-xs border" style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>Clear</button>
      </div>

      {/* ── Trade Log Table ───────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b" style={{ borderColor: '#1a2d4a' }}>
          <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>
            Trade Execution History ({trades.length})
          </h2>
        </div>
        {loading ? (
          <div className="text-center py-12 text-sm" style={{ color: '#8899b3' }}>Loading trades…</div>
        ) : trades.length === 0 ? (
          <div className="text-center py-10 space-y-1">
            <div className="text-3xl">📋</div>
            <p className="text-sm" style={{ color: '#8899b3' }}>No trades logged yet. Click "+ Log Trade" to start.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#8899b3', background: '#060b14' }}>
                  {['Date','Time','Symbol','Type','Product','Asset','Qty','Price','Total','Stop','Target','Brokerage','P&L','Status','Actions'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map(t => {
                  const pnl = t.realized_pnl || 0;
                  return (
                    <tr key={t.id} className="table-row-hover border-b" style={{ borderColor: '#0d1f36' }}>
                      <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#8899b3' }}>{t.trade_date}</td>
                      <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#8899b3' }}>{t.trade_time || '—'}</td>
                      <td className="px-3 py-2 font-semibold" style={{ color: '#e8f0fe' }}>{t.symbol}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded-full font-bold ${t.trade_type === 'BUY' ? 'badge-green' : 'badge-red'}`}>
                          {t.trade_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#8899b3' }}>{t.product_type}</td>
                      <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#8899b3' }}>{t.asset_category}</td>
                      <td className="px-3 py-2 font-mono">{t.quantity}</td>
                      <td className="px-3 py-2 font-mono">₹{t.price}</td>
                      <td className="px-3 py-2 font-mono">₹{t.total_value?.toLocaleString('en-IN')}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#ff1744' }}>{t.stop_loss ? `₹${t.stop_loss}` : '—'}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#00e676' }}>{t.target_price ? `₹${t.target_price}` : '—'}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#8899b3' }}>₹{t.brokerage}</td>
                      <td className={`px-3 py-2 font-bold font-mono ${pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-gray-500'}`}>
                        {pnl > 0 ? '+' : ''}₹{pnl}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          t.status === 'SQUARED_OFF' ? 'badge-green' :
                          t.status === 'OPEN'        ? 'badge-amber' :
                          t.status === 'CANCELLED'   ? 'badge-red'   : 'badge-blue'
                        }`}>{t.status}</span>
                      </td>
                      <td className="px-3 py-2 flex gap-1">
                        <button onClick={() => handleEdit(t)}
                          className="px-2 py-1 rounded text-xs border hover:bg-white/5 transition-all"
                          style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>Edit</button>
                        <button onClick={() => handleDelete(t.id)}
                          className="px-2 py-1 rounded text-xs hover:opacity-80"
                          style={{ background: 'rgba(255,23,68,0.15)', color: '#ff1744' }}>Del</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
