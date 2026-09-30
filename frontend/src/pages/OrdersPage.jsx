import { useEffect, useState } from 'react';
import {
  errorText,
  executePending,
  pendingOrders,
  placeIntraday,
  rejectPending,
  requestDelivery,
  requestSuggestion,
} from '../api/stockApi';

export default function OrdersPage({ user }) {
  const [orders, setOrders] = useState([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [delivery, setDelivery] = useState({ symbol: '', side: 'BUY', quantity: 1 });
  const [typed, setTyped] = useState({ symbol: '', side: 'BUY', quantity: 1 });
  const trader = user.role === 'trader';

  async function load() {
    try {
      setOrders(await pendingOrders());
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run(action) {
    setError('');
    setNote('');
    try {
      const result = await action();
      if (result?.detail) setNote(result.detail);
      await load();
    } catch (err) {
      setError(errorText(err));
    }
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
            <p className="muted">{order.quantity} shares · {order.product} · {order.source} · ₹{order.price}</p>
            {trader && (
              <div className="actions">
                <button type="button" className="primary" onClick={() => run(() => executePending(order.id))}>Execute</button>
                <button type="button" className="ghost" onClick={() => run(() => rejectPending(order.id))}>Reject</button>
              </div>
            )}
          </article>
        ))}
      </div>
      {trader && (
        <div className="grid">
          <form className="card" onSubmit={(event) => { event.preventDefault(); run(() => requestSuggestion()); }}>
            <h2>Ask for a suggestion</h2>
            <p className="muted">Saved as pending. It is not an order until you execute it.</p>
            <button type="submit" className="primary">Suggest one</button>
          </form>
          <form className="card" onSubmit={(event) => { event.preventDefault(); run(() => requestDelivery(delivery.symbol, delivery.side, Number(delivery.quantity))); }}>
            <h2>Delivery request</h2>
            <label>Symbol<input value={delivery.symbol} onChange={(event) => setDelivery({ ...delivery, symbol: event.target.value })} /></label>
            <label>Side
              <select value={delivery.side} onChange={(event) => setDelivery({ ...delivery, side: event.target.value })}>
                <option>BUY</option>
                <option>SELL</option>
              </select>
            </label>
            <label>Quantity<input type="number" min="1" value={delivery.quantity} onChange={(event) => setDelivery({ ...delivery, quantity: event.target.value })} /></label>
            <button type="submit" className="primary">Save request</button>
          </form>
          <form className="card" onSubmit={(event) => { event.preventDefault(); run(() => placeIntraday(typed.symbol, typed.side, Number(typed.quantity))); }}>
            <h2>Intraday order</h2>
            <p className="muted">This click places the order. It still has to pass the risk checks.</p>
            <label>Symbol<input value={typed.symbol} onChange={(event) => setTyped({ ...typed, symbol: event.target.value })} /></label>
            <label>Side
              <select value={typed.side} onChange={(event) => setTyped({ ...typed, side: event.target.value })}>
                <option>BUY</option>
                <option>SELL</option>
              </select>
            </label>
            <label>Quantity<input type="number" min="1" value={typed.quantity} onChange={(event) => setTyped({ ...typed, quantity: event.target.value })} /></label>
            <button type="submit" className="primary">Place intraday</button>
          </form>
        </div>
      )}
    </section>
  );
}
