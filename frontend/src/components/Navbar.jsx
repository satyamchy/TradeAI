import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { fetchMarketStatus, fetchMarketIndices, fetchGuardrailStatus, toggleTrading } from '../api/stockApi';

export default function Navbar() {
  const location = useLocation();
  const [marketStatus, setMarketStatus] = useState(null);
  const [indices, setIndices] = useState([]);
  const [guardrails, setGuardrails] = useState(null);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    async function initNavData() {
      try {
        const [status, idx, gr] = await Promise.all([
          fetchMarketStatus(),
          fetchMarketIndices(),
          fetchGuardrailStatus(),
        ]);
        setMarketStatus(status);
        setIndices(idx || []);
        setGuardrails(gr);
      } catch (e) {
        // Fallback or network error
      }
    }
    initNavData();
    const timer = setInterval(initNavData, 20000);
    return () => clearInterval(timer);
  }, []);

  const handleToggleKillSwitch = async () => {
    if (!guardrails) return;
    setToggling(true);
    try {
      const nextState = !guardrails.is_trading_enabled;
      const updated = await toggleTrading(nextState);
      setGuardrails(updated);
    } catch (err) {
      alert("Failed to toggle guardrail switch.");
    }
    setToggling(false);
  };

  const navLinks = [
    { to: '/chat', label: '💬 AI Agent Chat' },
    { to: '/analysis', label: '📊 Stock Analysis' },
    { to: '/trades', label: '💹 Live Trades & P&L' },
    { to: '/jobs', label: '⏱️ Jobs & Watchdog' },
  ];

  return (
    <header className="border-b" style={{ background: '#181411', borderColor: '#382e26' }}>
      {/* Ticker Tape */}
      {indices.length > 0 && (
        <div className="overflow-hidden border-b py-1 text-xs" style={{ background: '#12100e', borderColor: '#2e251e' }}>
          <div className="ticker-track flex gap-8 items-center">
            {indices.concat(indices).map((item, idx) => (
              <div key={idx} className="flex items-center gap-2 whitespace-nowrap">
                <span className="font-semibold" style={{ color: '#f5ebe1' }}>{item.symbol}</span>
                <span className="font-mono" style={{ color: '#ffaa00' }}>₹{item.current_price?.toLocaleString('en-IN')}</span>
                <span className={`text-[11px] font-mono ${item.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {item.change >= 0 ? '+' : ''}{item.change_pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Navbar */}
      <div className="max-w-7xl mx-auto px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <Link to="/chat" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center font-black text-base shadow"
                 style={{ background: 'linear-gradient(135deg, #ff6b00, #ffaa00)', color: '#12100e' }}>
              ⚡
            </div>
            <div>
              <div className="font-extrabold text-base tracking-wide flex items-center gap-1.5" style={{ color: '#f5ebe1' }}>
                TRADE<span style={{ color: '#ff6b00' }}>AI</span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded badge-orange uppercase">v2.0</span>
              </div>
              <div className="text-[10px]" style={{ color: '#a89b8c' }}>Indian Stock Market Intelligence</div>
            </div>
          </Link>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1.5">
          {navLinks.map((link) => {
            const isActive = location.pathname === link.to;
            return (
              <Link
                key={link.to}
                to={link.to}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  isActive
                    ? 'text-white shadow-sm'
                    : 'hover:text-white'
                }`}
                style={
                  isActive
                    ? { background: 'linear-gradient(135deg, #ff6b00, #e65100)', color: '#fff' }
                    : { color: '#a89b8c', background: 'transparent' }
                }
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Status Badges & Kill-Switch */}
        <div className="flex items-center gap-3">
          {/* Market Clock */}
          {marketStatus && (
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs"
                 style={{ background: '#1c1815', borderColor: '#382e26' }}>
              <span className={`w-2 h-2 rounded-full pulse-dot ${marketStatus.is_market_open ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              <span style={{ color: '#f5ebe1' }}>{marketStatus.current_time_ist} IST</span>
              <span className="text-[10px]" style={{ color: '#a89b8c' }}>({marketStatus.status})</span>
            </div>
          )}

          {/* Master Kill-Switch */}
          {guardrails && (
            <button
              onClick={handleToggleKillSwitch}
              disabled={toggling}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 border shadow-sm ${
                guardrails.is_trading_enabled
                  ? 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10'
                  : 'border-red-500/40 text-red-400 bg-red-500/10'
              }`}
              title="Click to toggle Master Kill-Switch"
            >
              <span className={`w-2 h-2 rounded-full ${guardrails.is_trading_enabled ? 'bg-emerald-400' : 'bg-red-500'}`} />
              {guardrails.is_trading_enabled ? 'LIVE TRADING ON' : 'KILL-SWITCH ACTIVE'}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
