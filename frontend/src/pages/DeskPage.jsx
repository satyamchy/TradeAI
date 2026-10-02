import { useEffect, useState } from 'react';
import {
  automationStatus,
  closePosition,
  disableAutomation,
  enableAutomation,
  errorText,
  funds,
  positions,
  squareOff,
} from '../api/stockApi';

export default function DeskPage({ user }) {
  const [status, setStatus] = useState(null);
  const [cash, setCash] = useState(null);
  const [book, setBook] = useState([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [methods, setMethods] = useState({ intraday_long: true, intraday_short: false });
  const [indexName, setIndexName] = useState('NIFTY 50');
  const trader = user.role === 'trader';
  const live = status?.mode === 'live';

  async function load() {
    try {
      const [nextStatus, nextCash, nextBook] = await Promise.all([
        automationStatus(),
        funds(),
        positions(),
      ]);
      setStatus(nextStatus);
      setCash(nextCash);
      setBook(nextBook.positions || []);
      if (nextStatus?.trading_index) setIndexName(nextStatus.trading_index);
      setError('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  async function run(name, action) {
    setBusy(name);
    setError('');
    setNote('');
    try {
      const result = await action();
      if (result?.order_id || result?.status) setNote(`${result.status || 'done'} ${result.order_id || ''}`.trim());
      await load();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy('');
    }
  }

  function chosenMethods() {
    return Object.entries(methods).filter(([, on]) => on).map(([name]) => name);
  }

  function onEnable() {
    const picked = chosenMethods();
    if (picked.length === 0) {
      setError('Choose long, short, or both.');
      return;
    }
    if (live && !window.confirm('Enable live entries on the selected index?')) return;
    run('enable', () => enableAutomation(picked, indexName));
  }

  function onSquareOff() {
    if (!window.confirm('Square off open intraday positions and stop new entries?')) return;
    run('square', squareOff);
  }

  return (
    <section>
      {live && <p className="banner">Live session. Orders go to this trader's Dhan account.</p>}
      <header className="page-head">
        <div>
          <p className="eyebrow">Desk</p>
          <h1>{status?.next_action?.replaceAll('_', ' ') || 'Loading'}</h1>
        </div>
        <div className="stat">
          <span>Cash</span>
          <strong>{cash ? `₹${Number(cash.available_balance_inr).toLocaleString('en-IN')}` : '—'}</strong>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {note && <p className="muted">{note}</p>}
      {status?.last_error && <p className="error">{status.last_error}</p>}
      <div className="grid">
        <article className="card">
          <h2>Automation</h2>
          <p className="muted">
            {status?.mode || 'paper'} mode. Entries are {status?.enabled ? 'on' : 'off'}.
            {status?.market_open ? ' The NSE session is open.' : ' The NSE session is closed.'}
            {status?.trading_index ? ` Index: ${status.trading_index}.` : ''}
          </p>
          {trader && (
            <>
              <label>Index
                <select value={indexName} onChange={(event) => setIndexName(event.target.value)}>
                  {(status?.indexes || ['NIFTY 50', 'NIFTY BANK', 'NIFTY NEXT 50', 'NIFTY FINANCIAL SERVICES', 'NIFTY MIDCAP 50']).map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </label>
              <label className="check"><input type="checkbox" checked={methods.intraday_long} onChange={(event) => setMethods({ ...methods, intraday_long: event.target.checked })} /> Intraday long</label>
              <label className="check"><input type="checkbox" checked={methods.intraday_short} onChange={(event) => setMethods({ ...methods, intraday_short: event.target.checked })} /> Intraday short</label>
              <div className="actions">
                <button type="button" className="primary" disabled={!!busy} onClick={onEnable}>Enable entries</button>
                <button type="button" className="ghost" disabled={!!busy} onClick={() => run('stop', disableAutomation)}>Stop entries</button>
                <button type="button" className="ghost" disabled={!!busy} onClick={onSquareOff}>Square off intraday</button>
              </div>
            </>
          )}
        </article>
        <article className="card">
          <h2>Open positions</h2>
          {book.length === 0 && <p className="muted">Nothing open.</p>}
          {book.map((row) => {
            const qty = Number(row.quantity);
            const side = qty > 0 ? 'LONG' : 'SHORT';
            const average = Number(row.average_price);
            const last = Number(row.last_price);
            const pnl = qty >= 0 ? (last - average) * qty : (average - last) * Math.abs(qty);
            return (
              <div className="row" key={`${row.symbol}-${row.product_type}`}>
                <div>
                  <strong>{row.symbol}</strong>
                  <span className="muted"> {side} · {row.product_type || 'INTRADAY'}</span>
                  <div className="muted">
                    {qty} @ ₹{average.toFixed(2)} · LTP ₹{last.toFixed(2)} · P&L ₹{pnl.toFixed(2)}
                  </div>
                </div>
                {trader && (
                  <button
                    type="button"
                    className="ghost"
                    disabled={!!busy}
                    onClick={() => run(row.symbol, () => closePosition(row.symbol, row.product_type || 'INTRADAY'))}
                  >
                    Close
                  </button>
                )}
              </div>
            );
          })}
        </article>
      </div>
    </section>
  );
}
