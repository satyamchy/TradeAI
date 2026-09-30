import { useEffect, useState } from 'react';
import { errorText, events } from '../api/stockApi';

export default function LogsPage({ user }) {
  const [rows, setRows] = useState([]);
  const [userId, setUserId] = useState('');
  const [error, setError] = useState('');

  async function load(target) {
    try {
      setRows(await events(target || undefined));
      setError('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="eyebrow">Logs</p>
          <h1>What changed</h1>
        </div>
        {user.role === 'admin' && (
          <form className="inline" onSubmit={(event) => { event.preventDefault(); load(userId); }}>
            <input placeholder="User id" value={userId} onChange={(event) => setUserId(event.target.value)} />
            <button type="submit" className="ghost">Read</button>
          </form>
        )}
      </header>
      {error && <p className="error">{error}</p>}
      <div className="table">
        {rows.length === 0 && <p className="muted">No events yet.</p>}
        {rows.map((row) => (
          <article className="log" key={row.id}>
            <div>
              <strong>{row.action}</strong>
              <span className="muted"> {row.status}</span>
            </div>
            <div className="muted">
              {row.created_at} · {row.symbol || '—'} {row.side || ''} {row.quantity || ''} {row.product || ''} · {row.mode}
            </div>
            {row.detail && <p>{row.detail}</p>}
          </article>
        ))}
      </div>
    </section>
  );
}
