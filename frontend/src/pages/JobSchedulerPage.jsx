import { useState, useEffect, useCallback } from 'react';
import { fetchJobs, createJob, triggerJob, deleteJob, fetchJobLogs } from '../api/stockApi';

const CRON_PRESETS = [
  { label: '09:00 AM IST — Pre-Market Scan',           cron: '0 9 * * 1-5'   },
  { label: '09:15 AM IST — Market Opening Signals',     cron: '15 9 * * 1-5'  },
  { label: '10:30 AM IST — Morning Mid-Session',        cron: '30 10 * * 1-5' },
  { label: '12:30 PM IST — Mid-Day Analysis',           cron: '30 12 * * 1-5' },
  { label: '02:00 PM IST — Afternoon Scan',             cron: '0 14 * * 1-5'  },
  { label: '03:00 PM IST — Pre-Close Check',            cron: '0 15 * * 1-5'  },
  { label: '03:15 PM IST — Intraday Auto Exit Check',   cron: '15 15 * * 1-5' },
  { label: '03:30 PM IST — Market Close Summary',       cron: '30 15 * * 1-5' },
  { label: 'Every 5 min (Market Hours)',                cron: '*/5 9-15 * * 1-5' },
];

const STATUS_COLOR = {
  SUCCESS:     'badge-green',
  FAILED:      'badge-red',
  IN_PROGRESS: 'badge-amber',
};

const emptyForm = {
  title: '',
  job_type: 'CRON',
  tickers: '',
  cron_expression: '15 9 * * 1-5',
  market_hours_only: true,
};

// ── Job Row ───────────────────────────────────────────────────────────────────
function JobRow({ job, onTrigger, onDelete }) {
  const [running, setRunning] = useState(false);
  const handleTrigger = async () => {
    setRunning(true);
    await onTrigger(job.id);
    setRunning(false);
  };
  return (
    <tr className="table-row-hover border-b" style={{ borderColor: '#0d1f36' }}>
      <td className="px-3 py-2">
        <div className="font-semibold text-sm" style={{ color: '#e8f0fe' }}>{job.title}</div>
        <div className="text-xs mt-0.5" style={{ color: '#8899b3' }}>{job.tickers}</div>
      </td>
      <td className="px-3 py-2">
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${job.job_type === 'CRON' ? 'badge-blue' : 'badge-purple'}`}>
          {job.job_type}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-xs" style={{ color: '#ffc107' }}>
        {job.cron_expression}
      </td>
      <td className="px-3 py-2 text-xs" style={{ color: '#8899b3' }}>
        {job.last_run ? new Date(job.last_run).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '—'}
      </td>
      <td className="px-3 py-2">
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${job.is_active ? 'badge-green' : 'badge-red'}`}>
          {job.is_active ? 'ACTIVE' : 'PAUSED'}
        </span>
      </td>
      <td className="px-3 py-2 flex gap-2">
        <button onClick={handleTrigger} disabled={running}
          className="px-3 py-1 rounded text-xs font-bold text-white disabled:opacity-50"
          style={{ background: '#2979ff' }}>
          {running ? '…' : '▶ Run'}
        </button>
        <button onClick={() => onDelete(job.id)}
          className="px-2 py-1 rounded text-xs"
          style={{ background: 'rgba(255,23,68,0.15)', color: '#ff1744' }}>Del</button>
      </td>
    </tr>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function JobSchedulerPage() {
  const [jobs,      setJobs]      = useState([]);
  const [logs,      setLogs]      = useState([]);
  const [form,      setForm]      = useState(emptyForm);
  const [showForm,  setShowForm]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [toast,     setToast]     = useState('');
  const [logJobId,  setLogJobId]  = useState(null);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 3500); };

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [j, l] = await Promise.all([fetchJobs(), fetchJobLogs(logJobId)]);
      setJobs(j.jobs || []);
      setLogs(l.logs || []);
    } catch (_) {}
    setLoading(false);
  }, [logJobId]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleFormChange = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handlePreset = (preset) => {
    setForm(f => ({
      ...f,
      cron_expression: preset.cron,
      title: f.title || preset.label,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.tickers) return showToast('Title and Tickers are required');
    try {
      await createJob(form);
      showToast(`✅ Job "${form.title}" created!`);
      setForm(emptyForm);
      setShowForm(false);
      loadAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Failed to create job');
    }
  };

  const handleTrigger = async (id) => {
    try {
      const res = await triggerJob(id);
      showToast(`▶ Job triggered! Log ID: ${res.log_id}`);
      loadAll();
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Trigger failed');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this job?')) return;
    await deleteJob(id);
    showToast('Job deleted.');
    loadAll();
  };

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      {/* Toast */}
      {toast && (
        <div className="fixed top-20 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium shadow-xl"
             style={{ background: '#0c1526', border: '1px solid #2979ff', color: '#e8f0fe' }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#e8f0fe' }}>⚙️ Jobs &amp; Cron Scheduler</h1>
          <p className="text-xs mt-0.5" style={{ color: '#8899b3' }}>
            Schedule AI analysis runs during Indian stock market hours · NSE/BSE Mon–Fri
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} className="px-3 py-1.5 rounded-lg text-xs border" style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>↻</button>
          <button onClick={() => setShowForm(f => !f)}
            className="px-4 py-1.5 rounded-lg text-sm font-semibold text-white"
            style={{ background: 'linear-gradient(135deg,#7c4dff,#2979ff)' }}>
            + Create Job
          </button>
        </div>
      </div>

      {/* ── Create Job Form ───────────────────────────────────────────── */}
      {showForm && (
        <div className="card p-4 space-y-4">
          <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>➕ New Analysis Job</h2>

          {/* Indian Market Presets */}
          <div>
            <div className="text-xs font-medium mb-2" style={{ color: '#8899b3' }}>
              🇮🇳 Indian Market Schedule Presets
            </div>
            <div className="flex flex-wrap gap-2">
              {CRON_PRESETS.map((p) => (
                <button key={p.cron} type="button" onClick={() => handlePreset(p)}
                  className={`px-3 py-1.5 rounded-lg text-xs border transition-all hover:border-blue-500/50 ${
                    form.cron_expression === p.cron
                      ? 'border-blue-500 text-blue-400 bg-blue-500/10'
                      : 'border-gray-700 text-gray-400'
                  }`}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Job Type toggle */}
              <div className="sm:col-span-2 lg:col-span-3 flex gap-2">
                {['NORMAL', 'CRON'].map(t => (
                  <button type="button" key={t} onClick={() => handleFormChange('job_type', t)}
                    className={`px-5 py-2 rounded-lg text-sm font-bold transition-all border ${
                      form.job_type === t ? 'badge-blue border-blue-500/50' : 'opacity-40 border-gray-700 text-gray-500'
                    }`}>
                    {t === 'NORMAL' ? '⚡ One-Time Instant' : '🔁 Recurring Cron'}
                  </button>
                ))}
              </div>

              {/* Title */}
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>Job Title</label>
                <input value={form.title} onChange={e => handleFormChange('title', e.target.value)}
                  placeholder="e.g. Pre-market NIFTY50 scan"
                  className="rounded-lg px-3 py-2 text-sm outline-none"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }} />
              </div>

              {/* Tickers */}
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>Tickers (comma-separated)</label>
                <input value={form.tickers} onChange={e => handleFormChange('tickers', e.target.value)}
                  placeholder="RELIANCE.NS,TCS.NS,HDFCBANK.NS"
                  className="rounded-lg px-3 py-2 text-sm outline-none"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }} />
              </div>

              {/* Cron Expression */}
              <div className="flex flex-col gap-1">
                <label className="text-xs" style={{ color: '#8899b3' }}>
                  Cron Expression
                  <span className="ml-1 text-amber-400 font-mono">({form.cron_expression})</span>
                </label>
                <input value={form.cron_expression} onChange={e => handleFormChange('cron_expression', e.target.value)}
                  placeholder="15 9 * * 1-5"
                  className="rounded-lg px-3 py-2 text-sm font-mono outline-none"
                  style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#ffc107' }} />
              </div>

              {/* Market Hours Only */}
              <div className="flex items-center gap-3 pt-5">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox"
                    checked={form.market_hours_only}
                    onChange={e => handleFormChange('market_hours_only', e.target.checked)}
                    className="w-4 h-4 accent-blue-500"
                  />
                  <span className="text-xs" style={{ color: '#8899b3' }}>
                    Only run during market hours (9:15 – 15:30 IST)
                  </span>
                </label>
              </div>
            </div>

            <div className="flex gap-3 mt-4">
              <button type="submit"
                className="px-5 py-2 rounded-lg text-sm font-bold text-white hover:opacity-90"
                style={{ background: 'linear-gradient(135deg,#7c4dff,#2979ff)' }}>
                💾 Create Job
              </button>
              <button type="button" onClick={() => { setShowForm(false); setForm(emptyForm); }}
                className="px-4 py-2 rounded-lg text-sm border" style={{ borderColor: '#1a2d4a', color: '#8899b3' }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Quick Reference: Indian Market Times ─────────────────────── */}
      <div className="card p-4">
        <h2 className="text-sm font-bold mb-3" style={{ color: '#e8f0fe' }}>🇮🇳 Indian Stock Market Schedule</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { time: '09:00', label: 'Pre-Market',      color: '#ffc107', desc: 'Order accumulation' },
            { time: '09:15', label: 'Market Opens',     color: '#00e676', desc: 'NSE/BSE live trading' },
            { time: '12:30', label: 'Mid-Day Scan',     color: '#2979ff', desc: 'Intraday re-evaluation' },
            { time: '15:15', label: 'Intraday Exit',    color: '#ff6d00', desc: 'Auto squareoff trigger' },
            { time: '15:30', label: 'Market Closes',    color: '#ff1744', desc: 'Regular session ends' },
            { time: '15:40', label: 'After-Market',     color: '#7c4dff', desc: 'AMO & post-session' },
          ].map(({ time, label, color, desc }) => (
            <div key={time} className="rounded-lg p-3" style={{ background: '#060b14', borderLeft: `3px solid ${color}` }}>
              <div className="font-mono font-bold text-sm" style={{ color }}>{time} IST</div>
              <div className="font-medium text-xs mt-1" style={{ color: '#e8f0fe' }}>{label}</div>
              <div className="text-xs mt-0.5" style={{ color: '#8899b3' }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Scheduled Jobs Table ──────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b" style={{ borderColor: '#1a2d4a' }}>
          <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>Active Jobs ({jobs.length})</h2>
        </div>
        {loading ? (
          <div className="text-center py-10 text-sm" style={{ color: '#8899b3' }}>Loading jobs…</div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-10 space-y-1">
            <div className="text-3xl">⏱️</div>
            <p className="text-sm" style={{ color: '#8899b3' }}>No jobs scheduled. Click "+ Create Job" to add one.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#8899b3', background: '#060b14' }}>
                  {['Job / Tickers', 'Type', 'Cron Expression', 'Last Run', 'Status', 'Actions'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <JobRow key={job.id} job={job} onTrigger={handleTrigger} onDelete={handleDelete} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Execution Log ─────────────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b flex flex-wrap items-center justify-between gap-2" style={{ borderColor: '#1a2d4a' }}>
          <h2 className="text-sm font-bold" style={{ color: '#e8f0fe' }}>Execution History ({logs.length})</h2>
          <div className="flex gap-2 items-center">
            <label className="text-xs" style={{ color: '#8899b3' }}>Filter Job ID:</label>
            <input type="number" value={logJobId || ''} onChange={e => setLogJobId(e.target.value || null)}
              placeholder="all"
              className="w-20 rounded px-2 py-1 text-xs outline-none"
              style={{ background: '#060b14', border: '1px solid #1a2d4a', color: '#e8f0fe' }} />
          </div>
        </div>
        {logs.length === 0 ? (
          <div className="text-center py-8 text-sm" style={{ color: '#8899b3' }}>No execution logs yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#8899b3', background: '#060b14' }}>
                  {['Log ID', 'Job ID', 'Status', 'Message', 'Executed At (IST)'].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map(l => (
                  <tr key={l.id} className="table-row-hover border-b" style={{ borderColor: '#0d1f36' }}>
                    <td className="px-3 py-2 font-mono" style={{ color: '#8899b3' }}>#{l.id}</td>
                    <td className="px-3 py-2 font-mono text-blue-400">#{l.job_id}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATUS_COLOR[l.status] || 'badge-blue'}`}>
                        {l.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 max-w-xs truncate" style={{ color: '#8899b3' }} title={l.message}>
                      {l.message}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap" style={{ color: '#8899b3' }}>
                      {l.executed_at ? new Date(l.executed_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
