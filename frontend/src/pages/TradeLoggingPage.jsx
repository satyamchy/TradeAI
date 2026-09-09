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
    <div className="card p-4 flex flex-col justify-between">
      <div>
        <div className="text-[11px] font-semibold tracking-wider uppercase mb-1" style={{ color: '#A89F91' }}>{label}</div>
        <div className={`text-2xl font-black font-mono ${color || ''}`} style={!color ? { color: '#F5EBE1' } : {}}>
          {value}
        </div>
      </div>
      {sub && <div className="text-xs font-mono mt-2" style={{ color: '#A89F91' }}>{sub}</div>}
    </div>
  );
}

// ── Open Position Row ─────────────────────────────────────────────────────────
function PositionRow({ pos, onSquareOff }) {
  const [exitPrice, setExitPrice] = useState('');
  const pnlColor = pos.unrealized_pnl >= 0 ? 'text-[#00E676]' : 'text-[#FF4D4D]';
  return (
    <tr className="table-row-hover border-b" style={{ borderColor: 'rgba(56, 46, 38, 0.4)' }}>
      <td className="px-3 py-2.5 font-bold font-mono text-sm" style={{ color: '#F5EBE1' }}>{pos.symbol}</td>
      <td className="px-3 py-2.5">
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${pos.trade_type === 'BUY' ? 'badge-green' : 'badge-red'}`}>
          {pos.trade_type}
        </span>
      </td>
      <td className="px-3 py-2.5 text-xs font-mono" style={{ color: '#A89F91' }}>{pos.product_type}</td>
      <td className="px-3 py-2.5 text-xs font-mono" style={{ color: '#F5EBE1' }}>₹{pos.entry_price}</td>
      <td className="px-3 py-2.5 text-xs font-mono" style={{ color: '#F5EBE1' }}>₹{pos.current_price}</td>
      <td className={`px-3 py-2.5 text-xs font-bold font-mono ${pnlColor}`}>
        {pos.unrealized_pnl >= 0 ? '+' : ''}₹{pos.unrealized_pnl}
      </td>
      <td className="px-3 py-2.5">
        {pos.needs_auto_squareoff && (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold badge-red animate-pulse">AUTO EXIT</span>
        )}
        {pos.recommendation === 'WATCH_STOP_LOSS' && (
          <span className="px-2 py-0.5 rounded text-[10px] badge-amber font-bold">STOP WATCH</span>
        )}
        {!pos.needs_auto_squareoff && pos.recommendation !== 'WATCH_STOP_LOSS' && (
          <span className="text-[11px] font-mono" style={{ color: '#A89F91' }}>HOLDING</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex gap-2 items-center">
          <input
            value={exitPrice} onChange={e => setExitPrice(e.target.value)}
            placeholder="Exit ₹" className="w-20 rounded px-2 py-1 text-xs font-mono outline-none"
            style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}
          />
          <button
            onClick={() => onSquareOff(pos.trade_id, exitPrice)}
            className="px-2.5 py-1 rounded text-xs font-bold transition-all hover:opacity-90"
            style={{ background: '#FF4D4D', color: '#FFFFFF' }}>
            Exit
          </button>
        </div>
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

  const pnlColor = (summary?.realized_pnl_inr || 0) >= 0 ? 'text-[#00E676]' : 'text-[#FF4D4D]';

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      {/* Toast Alert */}
      {toast && (
        <div className="fixed top-20 right-4 z-50 px-4 py-3 rounded-lg text-xs font-semibold shadow-2xl flex items-center gap-2"
             style={{ background: '#1C1815', border: '1px solid #FF6B00', color: '#F5EBE1', boxShadow: '0 10px 25px rgba(255, 107, 0, 0.2)' }}>
          <span className="text-[#FF6B00]">⚡</span>
          <span>{toast}</span>
        </div>
      )}

      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b" style={{ borderColor: '#382E26' }}>
        <div>
          <h1 className="text-xl font-black tracking-tight" style={{ color: '#F5EBE1' }}>
            <span className="text-[#FF6B00]">PORTFOLIO</span> &amp; TRADE EXECUTION
          </h1>
          <p className="text-xs font-mono mt-0.5" style={{ color: '#A89F91' }}>
            Multi-asset order management · Real-time P&amp;L · DhanHQ broker link
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:border-[#FF6B00]"
                  style={{ borderColor: '#382E26', color: '#A89F91', background: '#1C1815' }}>
            ↻ Refresh
          </button>
          <button
            onClick={() => { setShowForm(f => !f); setEditId(null); setForm(emptyForm); }}
            className="px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider text-black transition-all hover:opacity-90 shadow-md"
            style={{ background: 'linear-gradient(135deg, #FF6B00, #FF8533)' }}>
            + Log Trade
          </button>
        </div>
      </div>

      {/* ── Summary Stats ─────────────────────────────────────────────── */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <SummaryCard label="Total Trades" value={summary.total_trades}
            sub={`${summary.buy_count} LONG · ${summary.sell_count} SHORT`} />
          <SummaryCard label="Capital Deployed" value={`₹${(summary.total_capital_deployed_inr || 0).toLocaleString('en-IN')}`} />
          <SummaryCard label="Realized P&L"
            value={`${(summary.realized_pnl_inr || 0) >= 0 ? '+' : ''}₹${(summary.realized_pnl_inr || 0).toLocaleString('en-IN')}`}
            color={pnlColor} />
          <SummaryCard label="Win Rate" value={`${(summary.win_rate_pct || 0).toFixed(1)}%`} />
        </div>
      )}

      {/* ── Open Positions Monitor ────────────────────────────────────── */}
      {positions.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: '#382E26' }}>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#00E676] pulse-dot"></span>
              <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>Live Position Monitor ({positions.length})</h2>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded badge-amber">
              Intraday Auto-Exit at 3:15 PM IST
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#A89F91', background: '#12100E' }}>
                  {['Symbol','Type','Product','Entry Price','Current Price','Unrealized P&L','Risk Status','Square-Off'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>
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
        <div className="card p-4 space-y-4" style={{ borderColor: '#FF6B00' }}>
          <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: '#382E26' }}>
            <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>
              {editId ? '✏️ Modify Trade Record' : '➕ Log / Place New Trade'}
            </h2>
            <div className="flex items-center gap-2">
              {!guardrails?.is_trading_enabled && (
                <span className="text-[10px] px-2 py-1 rounded badge-red font-bold">
                  ⚠️ Live Trading OFF
                </span>
              )}
              {guardrails?.paper_trading_mode && (
                <span className="text-[10px] px-2 py-1 rounded badge-amber font-bold">📄 Paper Trading</span>
              )}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Trade Type toggle */}
            <div className="flex gap-2">
              {TRADE_TYPES.map(t => (
                <button type="button" key={t} onClick={() => handleFormChange('trade_type', t)}
                  className={`flex-1 py-2 rounded text-xs font-black tracking-wider uppercase transition-all ${
                    form.trade_type === t
                      ? t === 'BUY' ? 'badge-green !py-2 text-sm' : 'badge-red !py-2 text-sm'
                      : 'opacity-40 border border-[#382E26] text-[#A89F91]'
                  }`}>
                  {t === 'BUY' ? '↑ BUY / LONG' : '↓ SELL / SHORT'}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {[
                ['trade_date', 'Trade Date', 'date'],
                ['trade_time', 'Trade Time', 'time'],
                ['symbol',     'Symbol / Ticker', 'text'],
                ['quantity',   'Quantity (Shares)', 'number'],
                ['price',      'Execution Price (₹)', 'number'],
                ['stop_loss',  'Stop Loss (₹)', 'number'],
                ['target_price','Target Price (₹)', 'number'],
                ['brokerage',  'Brokerage & Tax (₹)', 'number'],
              ].map(([key, label, type]) => (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>{label}</label>
                  <input
                    type={type} value={form[key]}
                    onChange={e => handleFormChange(key, e.target.value)}
                    placeholder={key === 'symbol' ? 'RELIANCE.NS' : ''}
                    className="rounded px-3 py-2 text-xs font-mono outline-none focus:border-[#FF6B00]"
                    style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}
                  />
                </div>
              ))}

              {/* Product Type */}
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>Product Type</label>
                <select value={form.product_type} onChange={e => handleFormChange('product_type', e.target.value)}
                  className="rounded px-3 py-2 text-xs font-mono outline-none"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}>
                  {PROD_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              {/* Asset Category */}
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>Asset Category</label>
                <select value={form.asset_category} onChange={e => handleFormChange('asset_category', e.target.value)}
                  className="rounded px-3 py-2 text-xs font-mono outline-none"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}>
                  {ASSET_CATS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>

              {/* Notes */}
              <div className="col-span-2 sm:col-span-2 lg:col-span-2 flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>Strategy / Rationale</label>
                <input value={form.notes} onChange={e => handleFormChange('notes', e.target.value)}
                  placeholder="e.g. LangGraph 15m breakout entry..."
                  className="rounded px-3 py-2 text-xs outline-none w-full"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}
                />
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap gap-3 pt-2">
              <button type="submit"
                className="px-5 py-2 rounded text-xs font-bold uppercase tracking-wider text-white transition-all hover:opacity-90"
                style={{ background: '#FF6B00' }}>
                {editId ? 'Save Changes' : '💾 Log Trade Locally'}
              </button>
              {!editId && (
                <button type="button" onClick={handlePlaceOrder}
                  className="px-5 py-2 rounded text-xs font-bold uppercase tracking-wider transition-all hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg, #FFAA00, #FF6B00)', color: '#000000' }}>
                  🚀 Place via Broker (DhanHQ)
                </button>
              )}
              <button type="button" onClick={() => { setShowForm(false); setForm(emptyForm); setEditId(null); }}
                className="px-4 py-2 rounded text-xs border font-semibold transition-all hover:bg-white/5"
                style={{ borderColor: '#382E26', color: '#A89F91' }}>
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
            <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>{label}</label>
            <input type={type} value={filters[key]}
              onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}
              className="rounded px-3 py-1.5 text-xs outline-none"
              style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}
            />
          </div>
        ))}
        {[
          ['trade_type',    ['','BUY','SELL']],
          ['product_type',  ['','INTRADAY','DELIVERY']],
          ['asset_category',['','STOCK','GOLD','SILVER']],
        ].map(([key, opts]) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-[11px] font-semibold capitalize" style={{ color: '#A89F91' }}>{key.replace('_',' ')}</label>
            <select value={filters[key]} onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}
              className="rounded px-3 py-1.5 text-xs outline-none"
              style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}>
              {opts.map(o => <option key={o} value={o}>{o || 'All'}</option>)}
            </select>
          </div>
        ))}
        <button onClick={loadAll} className="px-4 py-1.5 rounded text-xs font-bold uppercase tracking-wider text-black"
                style={{ background: '#FF6B00' }}>Filter</button>
        <button onClick={() => { setFilters({ start_date:'',end_date:'',symbol:'',trade_type:'',product_type:'',asset_category:'' }); }}
          className="px-3 py-1.5 rounded text-xs border font-semibold" style={{ borderColor: '#382E26', color: '#A89F91' }}>Clear</button>
      </div>

      {/* ── Trade Log Table ───────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: '#382E26' }}>
          <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>
            Execution Ledger ({trades.length})
          </h2>
        </div>
        {loading ? (
          <div className="text-center py-12 text-xs font-mono" style={{ color: '#A89F91' }}>Loading trade records…</div>
        ) : trades.length === 0 ? (
          <div className="text-center py-10 space-y-1">
            <div className="text-3xl">📋</div>
            <p className="text-xs font-mono" style={{ color: '#A89F91' }}>No trades recorded. Click "+ Log Trade" to record an execution.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#A89F91', background: '#12100E' }}>
                  {['Date','Time','Symbol','Type','Product','Asset','Qty','Price','Total Val','Stop','Target','Brokerage','P&L','Status','Actions'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map(t => {
                  const pnl = t.realized_pnl || 0;
                  return (
                    <tr key={t.id} className="table-row-hover border-b" style={{ borderColor: 'rgba(56, 46, 38, 0.4)' }}>
                      <td className="px-3 py-2 font-mono whitespace-nowrap" style={{ color: '#A89F91' }}>{t.trade_date}</td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap" style={{ color: '#A89F91' }}>{t.trade_time || '—'}</td>
                      <td className="px-3 py-2 font-bold font-mono" style={{ color: '#F5EBE1' }}>{t.symbol}</td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${t.trade_type === 'BUY' ? 'badge-green' : 'badge-red'}`}>
                          {t.trade_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap" style={{ color: '#A89F91' }}>{t.product_type}</td>
                      <td className="px-3 py-2 font-mono whitespace-nowrap" style={{ color: '#A89F91' }}>{t.asset_category}</td>
                      <td className="px-3 py-2 font-mono">{t.quantity}</td>
                      <td className="px-3 py-2 font-mono">₹{t.price}</td>
                      <td className="px-3 py-2 font-mono">₹{t.total_value?.toLocaleString('en-IN')}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#FF4D4D' }}>{t.stop_loss ? `₹${t.stop_loss}` : '—'}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#00E676' }}>{t.target_price ? `₹${t.target_price}` : '—'}</td>
                      <td className="px-3 py-2 font-mono" style={{ color: '#A89F91' }}>₹{t.brokerage}</td>
                      <td className={`px-3 py-2 font-bold font-mono ${pnl > 0 ? 'text-[#00E676]' : pnl < 0 ? 'text-[#FF4D4D]' : 'text-gray-400'}`}>
                        {pnl > 0 ? '+' : ''}₹{pnl}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          t.status === 'SQUARED_OFF' ? 'badge-green' :
                          t.status === 'OPEN'        ? 'badge-amber' :
                          t.status === 'CANCELLED'   ? 'badge-red'   : 'badge-orange'
                        }`}>{t.status}</span>
                      </td>
                      <td className="px-3 py-2 flex gap-1">
                        <button onClick={() => handleEdit(t)}
                          className="px-2 py-1 rounded text-xs border hover:border-[#FF6B00] transition-all"
                          style={{ borderColor: '#382E26', color: '#A89F91' }}>Edit</button>
                        <button onClick={() => handleDelete(t.id)}
                          className="px-2 py-1 rounded text-xs hover:opacity-80"
                          style={{ background: 'rgba(255, 77, 77, 0.15)', color: '#FF4D4D' }}>Del</button>
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
