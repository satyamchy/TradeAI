import { useEffect, useState } from 'react';
import {
  automationSettings,
  errorText,
  patchAutomationSettings,
  saveDhanCredentials,
  session,
} from '../api/stockApi';

export default function SettingsPage({ user, onUser }) {
  const [limits, setLimits] = useState(null);
  const [clientId, setClientId] = useState('');
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    automationSettings().then(setLimits).catch((err) => setError(errorText(err)));
  }, []);

  async function saveCreds(event) {
    event.preventDefault();
    setError('');
    setMessage('');
    try {
      await saveDhanCredentials(clientId, token);
      setClientId('');
      setToken('');
      setMessage('Dhan credentials saved.');
      onUser(await session());
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function saveLimits(event) {
    event.preventDefault();
    setError('');
    try {
      setLimits(await patchAutomationSettings({
        max_positions: Number(limits.max_positions),
        capital_per_trade_pct: Number(limits.capital_per_trade_pct),
        max_daily_loss_inr: Number(limits.max_daily_loss_inr),
      }));
      setMessage('Limits saved.');
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Account</h1>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      {message && <p className="muted">{message}</p>}
      <div className="grid">
        {user.role === 'trader' && (
          <form className="card" onSubmit={saveCreds}>
            <h2>Dhan credentials</h2>
            <p className="muted">{user.dhan_saved ? 'A pair is already saved. Submitting replaces it.' : 'Nothing is saved yet.'}</p>
            <label>Client id<input value={clientId} onChange={(event) => setClientId(event.target.value)} autoComplete="off" /></label>
            <label>Access token<input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" /></label>
            <button type="submit" className="primary">Save</button>
          </form>
        )}
        <article className="card">
          <h2>Shared limits</h2>
          {!limits && <p className="muted">Loading</p>}
          {limits && user.role !== 'admin' && (
            <p className="muted">
              {limits.max_positions} positions, {limits.capital_per_trade_pct} of cash per trade,
              daily loss cap ₹{limits.max_daily_loss_inr}.
            </p>
          )}
          {limits && user.role === 'admin' && (
            <form onSubmit={saveLimits}>
              <label>Max positions<input type="number" min="1" value={limits.max_positions} onChange={(event) => setLimits({ ...limits, max_positions: event.target.value })} /></label>
              <label>Cash per trade<input type="number" step="0.01" value={limits.capital_per_trade_pct} onChange={(event) => setLimits({ ...limits, capital_per_trade_pct: event.target.value })} /></label>
              <label>Daily loss cap, INR<input type="number" value={limits.max_daily_loss_inr} onChange={(event) => setLimits({ ...limits, max_daily_loss_inr: event.target.value })} /></label>
              <button type="submit" className="primary">Save limits</button>
            </form>
          )}
        </article>
      </div>
    </section>
  );
}
