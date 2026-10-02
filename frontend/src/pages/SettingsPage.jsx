import { useEffect, useState } from 'react';
import {
  automationSettings,
  errorText,
  patchAutomationSettings,
  saveDhanCredentials,
  session,
} from '../api/stockApi';

const PERCENT_FIELDS = [
  ['capital_per_trade_pct', 'Cash per trade, percent'],
  ['cash_reserve_pct', 'Cash reserve, percent'],
  ['take_profit_pct', 'Take profit, percent'],
  ['stop_loss_pct', 'Stop loss, percent'],
];

function toForm(limits) {
  return {
    ...limits,
    capital_per_trade_pct: Number(limits.capital_per_trade_pct) * 100,
    cash_reserve_pct: Number(limits.cash_reserve_pct) * 100,
  };
}

export default function SettingsPage({ user, onUser }) {
  const [limits, setLimits] = useState(null);
  const [clientId, setClientId] = useState('');
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    automationSettings().then((rows) => setLimits(toForm(rows))).catch((err) => setError(errorText(err)));
  }, []);

  async function saveCreds(event) {
    event.preventDefault();
    setBusy(true);
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
    } finally {
      setBusy(false);
    }
  }

  async function saveLimits(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const saved = await patchAutomationSettings({
        max_positions: Number(limits.max_positions),
        capital_per_trade_pct: Number(limits.capital_per_trade_pct) / 100,
        cash_reserve_pct: Number(limits.cash_reserve_pct) / 100,
        take_profit_pct: Number(limits.take_profit_pct),
        stop_loss_pct: Number(limits.stop_loss_pct),
        max_daily_loss_inr: Number(limits.max_daily_loss_inr),
        screener_limit: Number(limits.screener_limit),
        cycle_interval_seconds: Number(limits.cycle_interval_seconds),
      });
      setLimits(toForm(saved));
      setMessage('Limits saved.');
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
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
            <p className="muted">{user.dhan_saved ? 'A pair is already saved. Submitting replaces it.' : 'Nothing is saved yet. Live orders use this pair only.'} Dhan expires this token after 24 hours. The desk renews it before that, while it is still valid.</p>
            <label>Client id<input value={clientId} onChange={(event) => setClientId(event.target.value)} autoComplete="off" /></label>
            <label>Access token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" /></label>
            <button type="submit" className="primary" disabled={busy}>Save</button>
          </form>
        )}
        <article className="card">
          <h2>Shared limits</h2>
          {!limits && <p className="muted">Loading</p>}
          {limits && user.role !== 'admin' && (
            <p className="muted">
              {limits.max_positions} positions, {limits.capital_per_trade_pct}% of cash per trade,
              reserve {limits.cash_reserve_pct}%, take profit {limits.take_profit_pct}%, stop {limits.stop_loss_pct}%,
              daily loss cap ₹{limits.max_daily_loss_inr}.
            </p>
          )}
          {limits && user.role === 'admin' && (
            <form onSubmit={saveLimits}>
              <label>Max positions<input type="number" min="1" value={limits.max_positions} onChange={(event) => setLimits({ ...limits, max_positions: event.target.value })} /></label>
              {PERCENT_FIELDS.map(([key, label]) => (
                <label key={key}>{label}<input type="number" step="0.1" value={limits[key]} onChange={(event) => setLimits({ ...limits, [key]: event.target.value })} /></label>
              ))}
              <label>Daily loss cap, INR<input type="number" value={limits.max_daily_loss_inr} onChange={(event) => setLimits({ ...limits, max_daily_loss_inr: event.target.value })} /></label>
              <label>Screener size<input type="number" min="1" value={limits.screener_limit} onChange={(event) => setLimits({ ...limits, screener_limit: event.target.value })} /></label>
              <label>Cycle interval, seconds<input type="number" min="30" value={limits.cycle_interval_seconds} onChange={(event) => setLimits({ ...limits, cycle_interval_seconds: event.target.value })} /></label>
              <button type="submit" className="primary" disabled={busy}>Save limits</button>
            </form>
          )}
        </article>
      </div>
    </section>
  );
}
