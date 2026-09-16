import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { fetchHoldings, fetchHoldingDetail } from '../api/stockApi';

function SummaryCard({ label, value, sub, color, icon }) {
  return (
    <div className="card p-4 flex flex-col justify-between">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold tracking-wider uppercase mb-1" style={{ color: '#A89F91' }}>
          {label}
        </div>
        {icon && <span className="text-base">{icon}</span>}
      </div>
      <div>
        <div className={`text-2xl font-black font-mono ${color || ''}`} style={!color ? { color: '#F5EBE1' } : {}}>
          {value}
        </div>
        {sub && <div className="text-xs font-mono mt-1" style={{ color: '#A89F91' }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function HoldingsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [pnlFilter, setPnlFilter] = useState('ALL');
  const [selectedStock, setSelectedStock] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadHoldings = useCallback(async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await fetchHoldings();
      setData(res);
    } catch (err) {
      console.error('Failed to fetch holdings:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadHoldings();
  }, [loadHoldings]);

  const handleSelectStock = async (stock) => {
    setSelectedStock(stock);
    setDetailLoading(true);
    try {
      const detailRes = await fetchHoldingDetail(stock.symbol);
      if (detailRes && detailRes.holding) {
        setSelectedStock(detailRes.holding);
      }
    } catch (err) {
      console.warn('Using existing stock data, detail fetch fallback:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  const holdings = data?.holdings || [];
  const summary = data?.summary || {
    total_investment: 0,
    current_value: 0,
    total_pnl: 0,
    total_pnl_pct: 0,
    day_pnl: 0,
    day_pnl_pct: 0,
    total_stocks: 0,
  };

  const filteredHoldings = holdings.filter((item) => {
    const matchSearch =
      item.symbol.toLowerCase().includes(search.toLowerCase()) ||
      (item.isin && item.isin.toLowerCase().includes(search.toLowerCase()));
    if (!matchSearch) return false;
    if (pnlFilter === 'PROFIT') return item.pnl > 0;
    if (pnlFilter === 'LOSS') return item.pnl < 0;
    return true;
  });

  const isProfit = summary.total_pnl >= 0;
  const isDayProfit = summary.day_pnl >= 0;

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b" style={{ borderColor: '#382E26' }}>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-black tracking-tight" style={{ color: '#F5EBE1' }}>
              DHAN <span className="text-[#FF6B00]">HOLDINGS</span>
            </h1>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                data?.is_live ? 'badge-green' : data?.status === 'warning' ? 'badge-amber' : 'badge-red'
              }`}
            >
              {data?.is_live ? '● Live Dhan Account' : data?.status === 'warning' ? '● Credentials Required' : '● Broker Offline'}
            </span>
          </div>
          <p className="text-xs font-mono mt-1" style={{ color: '#A89F91' }}>
            Delivered (DP) &amp; T1 quantities from DhanHQ account holdings API
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadHoldings(true)}
            disabled={refreshing}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:border-[#FF6B00] flex items-center gap-1.5"
            style={{ borderColor: '#382E26', color: '#A89F91', background: '#1C1815' }}
          >
            <span className={refreshing ? 'animate-spin' : ''}>↻</span>
            <span>{refreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>
          <Link
            to="/trades"
            className="px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider text-black transition-all hover:opacity-90 shadow-md"
            style={{ background: 'linear-gradient(135deg, #FF6B00, #FF8533)' }}
          >
            + Trade Now
          </Link>
        </div>
      </div>

      {/* Explicit Warning / Notice Banner */}
      {data?.warning && (
        <div
          className="p-3.5 rounded-lg text-xs font-mono flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border shadow-lg"
          style={{
            background: 'rgba(255, 170, 0, 0.08)',
            borderColor: 'rgba(255, 170, 0, 0.4)',
            color: '#FFAA00',
          }}
        >
          <div className="flex items-start sm:items-center gap-2.5">
            <span className="text-base">⚠️</span>
            <div>
              <span className="font-bold uppercase tracking-wide mr-2">[Warning]</span>
              <span>{data.warning}</span>
            </div>
          </div>
          {data.endpoint && (
            <span className="text-[10px] opacity-75 whitespace-nowrap bg-black/30 px-2 py-1 rounded">
              Endpoint: {data.endpoint}
            </span>
          )}
        </div>
      )}


      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard
          label="Current Value"
          value={`₹${(summary.current_value || 0).toLocaleString('en-IN')}`}
          sub={`${summary.total_stocks} Demat Stocks`}
          icon="💼"
        />
        <SummaryCard
          label="Total Invested"
          value={`₹${(summary.total_investment || 0).toLocaleString('en-IN')}`}
          sub="Capital Deployed"
          icon="💰"
        />
        <SummaryCard
          label="Total P&amp;L"
          value={`${isProfit ? '+' : ''}₹${(summary.total_pnl || 0).toLocaleString('en-IN')}`}
          sub={`${isProfit ? '▲ +' : '▼ '}${summary.total_pnl_pct || 0}% overall return`}
          color={isProfit ? 'text-[#00E676]' : 'text-[#FF4D4D]'}
          icon={isProfit ? '📈' : '📉'}
        />
        <SummaryCard
          label="Today's P&amp;L"
          value={`${isDayProfit ? '+' : ''}₹${(summary.day_pnl || 0).toLocaleString('en-IN')}`}
          sub={`${isDayProfit ? '▲ +' : '▼ '}${summary.day_pnl_pct || 0}% day change`}
          color={isDayProfit ? 'text-[#00E676]' : 'text-[#FF4D4D]'}
          icon="⏱️"
        />
      </div>

      {/* Search & Filter Controls */}
      <div className="card p-3 flex flex-wrap gap-3 items-center justify-between">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <span className="text-xs" style={{ color: '#A89F91' }}>Search:</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search stock or ISIN (e.g. RELIANCE)..."
            className="w-full rounded px-3 py-1.5 text-xs outline-none focus:border-[#FF6B00] font-mono"
            style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="text-xs px-2 py-1 rounded text-[#A89F91] hover:text-white"
            >
              ✕
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold mr-1" style={{ color: '#A89F91' }}>
            Filter:
          </span>
          {['ALL', 'PROFIT', 'LOSS'].map((f) => (
            <button
              key={f}
              onClick={() => setPnlFilter(f)}
              className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                pnlFilter === f
                  ? 'bg-[#FF6B00] text-black shadow-sm'
                  : 'border text-[#A89F91] hover:text-white'
              }`}
              style={pnlFilter !== f ? { borderColor: '#382E26', background: '#1C1815' } : {}}
            >
              {f === 'ALL' ? 'All Holdings' : f === 'PROFIT' ? 'Gainers' : 'Losers'}
            </button>
          ))}
        </div>
      </div>

      {/* Holdings Table */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: '#382E26' }}>
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>
              Holding Instruments ({filteredHoldings.length})
            </h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded badge-orange">
              Click stock for single stock view
            </span>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-xs font-mono" style={{ color: '#A89F91' }}>
            Loading Dhan account holdings...
          </div>
        ) : filteredHoldings.length === 0 ? (
          <div className="text-center py-12 px-4 space-y-3">
            <div className="text-3xl">{data?.warning ? '⚠️' : '📂'}</div>
            <p className="text-xs font-mono font-medium max-w-md mx-auto" style={{ color: data?.warning ? '#FFAA00' : '#A89F91' }}>
              {data?.warning
                ? data.warning
                : search || pnlFilter !== 'ALL'
                ? 'No holdings match your search/filter.'
                : 'No delivery holdings found in this Dhan account.'}
            </p>
            {data?.warning && (
              <p className="text-[11px] font-mono" style={{ color: '#A89F91' }}>
                Update <code className="text-[#FF6B00]">backend/.env</code> with your Dhan keys to load live portfolio data.
              </p>
            )}
          </div>

        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#A89F91', background: '#12100E' }}>
                  {['Instrument', 'Exchange', 'Total Qty', 'DP Qty', 'T1 Qty', 'Avg Price', 'LTP', 'Current Val', 'Net P&L', 'Day P&L', 'Details'].map((h) => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredHoldings.map((item) => {
                  const pnl = item.pnl || 0;
                  const pnlPct = item.pnl_pct || 0;
                  const dayPnl = item.day_pnl || 0;
                  const dayPct = item.day_pnl_pct || 0;
                  const isPos = pnl >= 0;
                  const isDayPos = dayPnl >= 0;

                  return (
                    <tr
                      key={item.symbol + item.isin}
                      onClick={() => handleSelectStock(item)}
                      className="table-row-hover border-b cursor-pointer transition-colors"
                      style={{ borderColor: 'rgba(56, 46, 38, 0.4)' }}
                    >
                      <td className="px-3 py-2.5 font-bold font-mono text-sm whitespace-nowrap" style={{ color: '#F5EBE1' }}>
                        <div>{item.symbol}</div>
                        {item.isin && item.isin !== '—' && (
                          <div className="text-[10px] font-mono font-normal opacity-60">{item.isin}</div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold border border-[#382E26] text-[#A89F91]">
                          {item.exchange}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono font-bold whitespace-nowrap" style={{ color: '#F5EBE1' }}>
                        {item.total_qty}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: '#A89F91' }}>
                        {item.dp_qty}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap">
                        {item.t1_qty > 0 ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold badge-amber">
                            +{item.t1_qty} T1
                          </span>
                        ) : (
                          <span style={{ color: '#A89F91' }}>0</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: '#F5EBE1' }}>
                        ₹{item.avg_price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap font-bold" style={{ color: '#FFAA00' }}>
                        ₹{item.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: '#F5EBE1' }}>
                        ₹{item.current_value?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className={`px-3 py-2.5 font-mono whitespace-nowrap font-bold ${isPos ? 'text-[#00E676]' : 'text-[#FF4D4D]'}`}>
                        <div>{isPos ? '+' : ''}₹{pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                        <div className="text-[10px] font-normal">
                          {isPos ? '+' : ''}{pnlPct}%
                        </div>
                      </td>
                      <td className={`px-3 py-2.5 font-mono whitespace-nowrap ${isDayPos ? 'text-[#00E676]' : 'text-[#FF4D4D]'}`}>
                        <div>{isDayPos ? '+' : ''}₹{dayPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                        <div className="text-[10px]">
                          {isDayPos ? '+' : ''}{dayPct}%
                        </div>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectStock(item);
                          }}
                          className="px-2.5 py-1 rounded text-[11px] font-semibold border transition-all hover:border-[#FF6B00] hover:text-[#FF6B00]"
                          style={{ borderColor: '#382E26', color: '#A89F91', background: '#12100E' }}
                        >
                          View ➔
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Single Stock Detail Modal */}
      {selectedStock && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          onClick={() => setSelectedStock(null)}
        >
          <div
            className="card max-w-lg w-full p-5 space-y-4 shadow-2xl relative"
            style={{ background: '#181411', borderColor: '#FF6B00', boxShadow: '0 20px 40px rgba(0,0,0,0.8)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: '#382E26' }}>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-black font-mono" style={{ color: '#F5EBE1' }}>
                    {selectedStock.symbol}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold border border-[#382E26] text-[#FFAA00]">
                    {selectedStock.exchange || 'NSE'}
                  </span>
                  {detailLoading && (
                    <span className="text-[10px] font-mono text-[#A89F91] animate-pulse">updating...</span>
                  )}
                </div>
                <div className="text-xs font-mono mt-0.5" style={{ color: '#A89F91' }}>
                  ISIN: {selectedStock.isin || '—'} {selectedStock.security_id ? `· Security ID: ${selectedStock.security_id}` : ''}
                </div>
              </div>
              <button
                onClick={() => setSelectedStock(null)}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-[#A89F91] hover:text-white border hover:border-[#FF6B00]"
                style={{ borderColor: '#382E26', background: '#12100E' }}
              >
                ✕
              </button>
            </div>

            {/* Price & PnL Highlight Banner */}
            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg" style={{ background: '#12100E', border: '1px solid #2E251E' }}>
              <div>
                <div className="text-[10px] uppercase font-semibold" style={{ color: '#A89F91' }}>Current Market Price (LTP)</div>
                <div className="text-xl font-black font-mono mt-0.5" style={{ color: '#FFAA00' }}>
                  ₹{selectedStock.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className="text-[11px] font-mono mt-0.5" style={{ color: '#A89F91' }}>
                  Avg Buy: ₹{selectedStock.avg_price?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase font-semibold" style={{ color: '#A89F91' }}>Unrealized Return (P&amp;L)</div>
                <div className={`text-xl font-black font-mono mt-0.5 ${(selectedStock.pnl || 0) >= 0 ? 'text-[#00E676]' : 'text-[#FF4D4D]'}`}>
                  {(selectedStock.pnl || 0) >= 0 ? '+' : ''}₹{selectedStock.pnl?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div className={`text-[11px] font-mono font-bold mt-0.5 ${(selectedStock.pnl_pct || 0) >= 0 ? 'text-[#00E676]' : 'text-[#FF4D4D]'}`}>
                  {(selectedStock.pnl_pct || 0) >= 0 ? '▲ +' : '▼ '}{selectedStock.pnl_pct}%
                </div>
              </div>
            </div>

            {/* Detailed Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs font-mono">
              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>Total Quantity</div>
                <div className="font-bold text-sm mt-0.5" style={{ color: '#F5EBE1' }}>{selectedStock.total_qty}</div>
              </div>
              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>Delivered / DP Qty</div>
                <div className="font-bold text-sm mt-0.5" style={{ color: '#00E676' }}>{selectedStock.dp_qty}</div>
              </div>
              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>T1 Settlement Qty</div>
                <div className="font-bold text-sm mt-0.5" style={{ color: '#FFAA00' }}>{selectedStock.t1_qty || 0}</div>
              </div>

              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>Invested Value</div>
                <div className="font-bold text-sm mt-0.5" style={{ color: '#F5EBE1' }}>
                  ₹{selectedStock.invested_value?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>Current Market Value</div>
                <div className="font-bold text-sm mt-0.5" style={{ color: '#F5EBE1' }}>
                  ₹{selectedStock.current_value?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div className="p-2.5 rounded border" style={{ background: '#1C1815', borderColor: '#382E26' }}>
                <div className="text-[10px]" style={{ color: '#A89F91' }}>Day's P&amp;L</div>
                <div className={`font-bold text-sm mt-0.5 ${(selectedStock.day_pnl || 0) >= 0 ? 'text-[#00E676]' : 'text-[#FF4D4D]'}`}>
                  {(selectedStock.day_pnl || 0) >= 0 ? '+' : ''}₹{selectedStock.day_pnl?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center gap-2 pt-2 border-t" style={{ borderColor: '#382E26' }}>
              <Link
                to={`/analysis?ticker=${selectedStock.symbol}.NS`}
                className="flex-1 text-center py-2 rounded text-xs font-bold uppercase tracking-wider text-black transition-all hover:opacity-90 shadow-md"
                style={{ background: 'linear-gradient(135deg, #FFAA00, #FF6B00)' }}
              >
                📊 AI Stock Analysis
              </Link>
              <Link
                to="/trades"
                className="flex-1 text-center py-2 rounded text-xs font-bold uppercase tracking-wider transition-all hover:opacity-90 border"
                style={{ borderColor: '#382E26', color: '#F5EBE1', background: '#1C1815' }}
              >
                💹 Order / Trade
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

