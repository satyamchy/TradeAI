import { useEffect, useState } from 'react';
import {
  automationStatus,
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
  const trader = user.role === 'trader';

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
      setError('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run(action) {
    setError('');
    try {
      await action();
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
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
      <div className="grid">
        <article className="card">
          <h2>Automation</h2>
          <p className="muted">
            {status?.mode || 'paper'} mode. Entries are {status?.enabled ? 'on' : 'off'}.
            {status?.market_open ? ' The NSE session is open.' : ' The NSE session is closed.'}
          </p>
          {trader && (
            <div className="actions">
              <button type="button" className="primary" onClick={() => run(() => enableAutomation(['intraday_long', 'intraday_short']))}>
                Enable entries
              </button>
              <button type="button" className="ghost" onClick={() => run(disableAutomation)}>Stop entries</button>
              <button type="button" className="ghost" onClick={() => run(squareOff)}>Square off intraday</button>
            </div>
          )}
        </article>
        <article className="card">
          <h2>Open positions</h2>
          {book.length === 0 && <p className="muted">Nothing open.</p>}
          {book.map((row) => (
            <div className="row" key={`${row.symbol}-${row.product_type}`}>
              <div>
                <strong>{row.symbol}</strong>
                <span className="muted"> {row.product_type || 'INTRADAY'}</span>
              </div>
              <span>{row.quantity}</span>
            </div>
          ))}
        </article>
      </div>
    </section>
  );
}
