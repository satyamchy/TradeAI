import { useEffect, useState } from 'react';
import {
  accountOrders,
  cancelOrder,
  errorText,
  executePending,
  pendingOrders,
  placeIntraday,
  rejectPending,
  requestDelivery,
  requestSuggestion,
} from '../api/stockApi';

const WORKING = ['PENDING', 'TRANSIT', 'OPEN', 'PART_TRADED'];

export default function OrdersPage({ user }) {
  const [orders, setOrders] = useState([]);
  const [fills, setFills] = useState([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [delivery, setDelivery] = useState({ symbol: '', side: 'BUY', quantity: '1' });
  const [typed, setTyped] = useState({ symbol: '', side: 'BUY', quantity: '1' });
  const trader = user.role === 'trader';

  async function load() {
    try {
      const [pending, blotter] = await Promise.all([pendingOrders(), accountOrders()]);
      setOrders(pending);
      setFills(blotter.orders || []);
      setError('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run(name, action) {
    setBusy(name);
    setError('');
    setNote('');
    try {
      const result = await action();
      const status = result?.order?.status || result?.status;
      const id = result?.order?.order_id || result?.order_id;
      if (status || id) setNote(`${status || 'done'}${id ? ` ${id}` : ''}`);
      else if (result?.detail) setNote(result.detail);
      else if (result?.symbol) setNote(`${result.symbol} ${result.side || ''} saved`.trim());
      await load();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy('');
    }
  }

  function shares(value) {
    const quantity = Number(value);
    if (!Number.isInteger(quantity) || quantity < 1) {
      setError('Quantity must be a whole number of shares.');
      return null;
    }
    return quantity;
  }

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="eyebrow">Orders</p>
          <h1>Waiting for you</h1>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {note && <p className="muted">{note}</p>}
      <div className="stack">
        {orders.length === 0 && <article className="card"><p className="muted">No pending suggestion or delivery request.</p></article>}
        {orders.map((order) => (
          <article className="card" key={order.id}>
            <h2>{order.symbol} {order.side}</h2>
            <p>{order.detail || `${order.source} · ${order.product}`}</p>
            <p className="muted">{order.quantity} shares · {order.product} · {order.source} · {order.status} · saved ₹{order.price}</p>
            {trader && order.status === 'pending' && (
              <div className="actions">
                <button type="button" className="primary" disabled={!!busy} onClick={() => run(`exec-${order.id}`, () => executePending(order.id))}>Execute</button>
                <button type="button" className="ghost" disabled={!!busy} onClick={() => run(`rej-${order.id}`, () => rejectPending(order.id))}>Reject</button>
              </div>
            )}
          </article>
        ))}
      </div>
      <article className="card">
        <h2>Orders</h2>
        {fills.length === 0 && <p className="muted">No orders yet.</p>}
        {fills.map((order) => (
          <div className="row" key={order.order_id}>
            <div>
              <strong>{order.symbol || order.order_id}</strong>
              <span className="muted"> {order.side} {order.quantity} · {order.product_type} · {order.status}</span>
            </div>
            {trader && WORKING.includes(String(order.status || '').toUpperCase()) && (
              <button type="button" className="ghost" disabled={!!busy} onClick={() => run(order.order_id, () => cancelOrder(order.order_id))}>Cancel</button>
            )}
          </div>
        ))}
      </article>
      {trader && (
        <div className="grid">
          <form className="card" onSubmit={(event) => { event.preventDefault(); run('suggest', requestSuggestion); }}>
            <h2>Ask for a suggestion</h2>
            <p className="muted">Saved as pending. It is not an order until you execute it.</p>
            <button type="submit" className="primary" disabled={!!busy}>Suggest one</button>
          </form>
          <form className="card" onSubmit={(event) => {
            event.preventDefault();
            const quantity = shares(delivery.quantity);
            if (quantity) run('delivery', () => requestDelivery(delivery.symbol, delivery.side, quantity));
          }}>
            <h2>Delivery request</h2>
            <label>Symbol<input value={delivery.symbol} onChange={(event) => setDelivery({ ...delivery, symbol: event.target.value })} /></label>
            <label>Side
              <select value={delivery.side} onChange={(event) => setDelivery({ ...delivery, side: event.target.value })}>
                <option>BUY</option>
                <option>SELL</option>
              </select>
            </label>
            <label>Quantity<input type="number" min="1" step="1" value={delivery.quantity} onChange={(event) => setDelivery({ ...delivery, quantity: event.target.value })} /></label>
            <button type="submit" className="primary" disabled={!!busy}>Save request</button>
          </form>
          <form className="card" onSubmit={(event) => {
            event.preventDefault();
            const quantity = shares(typed.quantity);
            if (!quantity) return;
            if (!window.confirm(`Place ${typed.side} ${quantity} ${typed.symbol || ''} intraday?`)) return;
            run('intraday', () => placeIntraday(typed.symbol, typed.side, quantity));
          }}>
            <h2>Intraday order</h2>
            <p className="muted">This click places the order. It still has to pass the risk checks.</p>
            <label>Symbol<input value={typed.symbol} onChange={(event) => setTyped({ ...typed, symbol: event.target.value })} /></label>
            <label>Side
              <select value={typed.side} onChange={(event) => setTyped({ ...typed, side: event.target.value })}>
                <option>BUY</option>
                <option>SELL</option>
              </select>
            </label>
            <label>Quantity<input type="number" min="1" step="1" value={typed.quantity} onChange={(event) => setTyped({ ...typed, quantity: event.target.value })} /></label>
            <button type="submit" className="primary" disabled={!!busy}>Place intraday</button>
          </form>
        </div>
      )}
    </section>
  );
}
