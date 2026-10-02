import { useEffect, useState } from 'react';
import { createUser, errorText, updateUser, users } from '../api/stockApi';

export default function UsersPage() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ username: '', password: '', role: 'trader' });
  const [error, setError] = useState('');

  async function load() {
    try {
      setRows(await users());
      setError('');
    } catch (err) {
      setError(errorText(err));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add(event) {
    event.preventDefault();
    try {
      await createUser(form);
      setForm({ username: '', password: '', role: 'trader' });
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function toggle(row) {
    const disabling = !row.disabled;
    if (disabling && !window.confirm(`Disable ${row.username}? Open intraday positions stay in the exit loop until they are flat.`)) return;
    try {
      await updateUser(row.id, { disabled: disabling });
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function changeRole(row, role) {
    if (role === row.role) return;
    if (row.role === 'trader' && !window.confirm('This account will stop opening positions. Open intraday risk is flattened on the next pass.')) return;
    try {
      await updateUser(row.id, { role });
      await load();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <header className="page-head">
        <div>
          <p className="eyebrow">Users</p>
          <h1>Accounts</h1>
        </div>
      </header>
      {error && <p className="error">{error}</p>}
      <div className="stack">
        {rows.map((row) => (
          <article className="card row" key={row.id}>
            <div>
              <strong>{row.username}</strong>
              <span className="muted"> {row.role}{row.disabled ? ' · disabled' : ''}</span>
            </div>
            <select value={row.role} onChange={(event) => changeRole(row, event.target.value)}>
              <option value="trader">trader</option>
              <option value="viewer">viewer</option>
              <option value="admin">admin</option>
            </select>
            <button type="button" className="ghost" onClick={() => toggle(row)}>
              {row.disabled ? 'Enable' : 'Disable'}
            </button>
          </article>
        ))}
      </div>
      <form className="card" onSubmit={add}>
        <h2>New account</h2>
        <label>Username<input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
        <label>Password<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
        <label>Role
          <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
            <option value="trader">trader</option>
            <option value="viewer">viewer</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button type="submit" className="primary">Create</button>
      </form>
    </section>
  );
}
