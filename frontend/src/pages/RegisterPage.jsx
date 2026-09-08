import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.js';

function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({ email: '', password: '' });

  // Creates an account and redirects to the chat workspace.
  async function handleSubmit(event) {
    event.preventDefault();
    await register(form);
    navigate('/chat');
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-2xl bg-slate-900 p-8 shadow-xl">
        <h1 className="text-2xl font-semibold text-white">Create your ONEAI account</h1>
        <input className="mt-6 w-full rounded-lg bg-slate-800 p-3 text-white" placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
        <input className="mt-3 w-full rounded-lg bg-slate-800 p-3 text-white" type="password" placeholder="Password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        <button className="mt-5 w-full rounded-lg bg-blue-600 p-3 font-medium text-white">Register</button>
        <p className="mt-4 text-sm text-slate-400">Already registered? <Link className="text-blue-400" to="/login">Login</Link></p>
      </form>
    </main>
  );
}

export default RegisterPage;
