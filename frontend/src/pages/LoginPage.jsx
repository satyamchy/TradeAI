import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.js';

function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });

  // Submits credentials and redirects to chat on success.
  async function handleSubmit(event) {
    event.preventDefault();
    await login(form);
    navigate('/chat');
  }

  // Guest mode is a local UI-only exploration path until backend guest auth is added.
  function enterGuestMode() {
    localStorage.setItem('paios_token', 'guest');
    navigate('/chat');
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-2xl bg-slate-900 p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-white">Login to ONEAI</h1>
        <p className="mt-2 text-sm text-slate-400">Use your account, or explore the UI in guest mode.</p>
        <input className="mt-6 w-full rounded-lg bg-slate-800 p-3 text-white" placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        <input className="mt-3 w-full rounded-lg bg-slate-800 p-3 text-white" type="password" placeholder="Password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        <button className="mt-5 w-full rounded-lg bg-blue-600 p-3 font-medium text-white">Login</button>
        <button type="button" onClick={enterGuestMode} className="mt-3 w-full rounded-lg border border-slate-700 p-3 text-slate-200">Explore without login</button>
        <p className="mt-4 text-sm text-slate-400">No account? <Link className="text-blue-400" to="/register">Register</Link></p>
      </form>
    </main>
  );
}

export default LoginPage;
