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
    <tr className="table-row-hover border-b" style={{ borderColor: 'rgba(56, 46, 38, 0.4)' }}>
      <td className="px-3 py-2.5">
        <div className="font-bold text-xs font-mono" style={{ color: '#F5EBE1' }}>{job.title}</div>
        <div className="text-[11px] font-mono mt-0.5" style={{ color: '#A89F91' }}>{job.tickers}</div>
      </td>
      <td className="px-3 py-2.5">
        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${job.job_type === 'CRON' ? 'badge-orange' : 'badge-amber'}`}>
          {job.job_type}
        </span>
      </td>
      <td className="px-3 py-2.5 font-mono text-xs font-bold" style={{ color: '#FFAA00' }}>
        {job.cron_expression}
      </td>
      <td className="px-3 py-2.5 text-xs font-mono" style={{ color: '#A89F91' }}>
        {job.last_run ? new Date(job.last_run).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : '—'}
      </td>
      <td className="px-3 py-2.5">
        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${job.is_active ? 'badge-green' : 'badge-red'}`}>
          {job.is_active ? 'ACTIVE' : 'PAUSED'}
        </span>
      </td>
      <td className="px-3 py-2.5 flex gap-2">
        <button onClick={handleTrigger} disabled={running}
          className="px-3 py-1 rounded text-xs font-bold uppercase tracking-wider text-black disabled:opacity-50"
          style={{ background: '#FF6B00' }}>
          {running ? '…' : '▶ Run'}
        </button>
        <button onClick={() => onDelete(job.id)}
          className="px-2 py-1 rounded text-xs font-semibold hover:opacity-80"
          style={{ background: 'rgba(255, 77, 77, 0.15)', color: '#FF4D4D' }}>Del</button>
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
        <div className="fixed top-20 right-4 z-50 px-4 py-3 rounded-lg text-xs font-semibold shadow-2xl flex items-center gap-2"
             style={{ background: '#1C1815', border: '1px solid #FF6B00', color: '#F5EBE1', boxShadow: '0 10px 25px rgba(255, 107, 0, 0.2)' }}>
          <span className="text-[#FF6B00]">⚡</span>
          <span>{toast}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b" style={{ borderColor: '#382E26' }}>
        <div>
          <h1 className="text-xl font-black tracking-tight" style={{ color: '#F5EBE1' }}>
            <span className="text-[#FF6B00]">JOB RUNNER</span> &amp; CRON SCHEDULER
          </h1>
          <p className="text-xs font-mono mt-0.5" style={{ color: '#A89F91' }}>
            Periodic AI stock scans · Scheduled signal generation · Market hours execution
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} className="px-3 py-1.5 rounded-lg text-xs font-medium border transition-all hover:border-[#FF6B00]"
                  style={{ borderColor: '#382E26', color: '#A89F91', background: '#1C1815' }}>
            ↻ Refresh
          </button>
          <button onClick={() => setShowForm(f => !f)}
            className="px-4 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider text-black transition-all hover:opacity-90 shadow-md"
            style={{ background: 'linear-gradient(135deg, #FF6B00, #FF8533)' }}>
            + Create Job
          </button>
        </div>
      </div>

      {/* ── Create Job Form ───────────────────────────────────────────── */}
      {showForm && (
        <div className="card p-4 space-y-4" style={{ borderColor: '#FF6B00' }}>
          <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>➕ New Analysis Job</h2>

          {/* Indian Market Presets */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: '#A89F91' }}>
              🇮🇳 Indian Market Schedule Presets
            </div>
            <div className="flex flex-wrap gap-2">
              {CRON_PRESETS.map((p) => (
                <button key={p.cron} type="button" onClick={() => handlePreset(p)}
                  className={`px-3 py-1.5 rounded text-xs font-mono transition-all border ${
                    form.cron_expression === p.cron
                      ? 'border-[#FF6B00] text-[#FF6B00] bg-[#FF6B00]/10 font-bold'
                      : 'border-[#382E26] text-[#A89F91] hover:border-[#FFAA00]'
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
                    className={`px-5 py-2 rounded text-xs font-black tracking-wider uppercase transition-all border ${
                      form.job_type === t ? 'border-[#FF6B00] text-[#FF6B00] bg-[#FF6B00]/10' : 'opacity-40 border-[#382E26] text-[#A89F91]'
                    }`}>
                    {t === 'NORMAL' ? '⚡ One-Time Run' : '🔁 Recurring Cron'}
                  </button>
                ))}
              </div>

              {/* Title */}
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>Job Title</label>
                <input value={form.title} onChange={e => handleFormChange('title', e.target.value)}
                  placeholder="e.g. Pre-market NIFTY50 scan"
                  className="rounded px-3 py-2 text-xs font-mono outline-none focus:border-[#FF6B00]"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }} />
              </div>

              {/* Tickers */}
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>Tickers (comma-separated)</label>
                <input value={form.tickers} onChange={e => handleFormChange('tickers', e.target.value)}
                  placeholder="RELIANCE.NS,TCS.NS,HDFCBANK.NS"
                  className="rounded px-3 py-2 text-xs font-mono outline-none focus:border-[#FF6B00]"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }} />
              </div>

              {/* Cron Expression */}
              <div className="flex flex-col gap-1">
                <label className="text-[11px] font-semibold" style={{ color: '#A89F91' }}>
                  Cron Expression
                  <span className="ml-1 text-[#FFAA00] font-mono">({form.cron_expression})</span>
                </label>
                <input value={form.cron_expression} onChange={e => handleFormChange('cron_expression', e.target.value)}
                  placeholder="15 9 * * 1-5"
                  className="rounded px-3 py-2 text-xs font-mono outline-none focus:border-[#FF6B00]"
                  style={{ background: '#12100E', border: '1px solid #382E26', color: '#FFAA00' }} />
              </div>

              {/* Market Hours Only */}
              <div className="flex items-center gap-3 pt-5">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox"
                    checked={form.market_hours_only}
                    onChange={e => handleFormChange('market_hours_only', e.target.checked)}
                    className="w-4 h-4 accent-[#FF6B00]"
                  />
                  <span className="text-xs font-mono" style={{ color: '#A89F91' }}>
                    Only run during NSE/BSE market hours (9:15 – 15:30 IST)
                  </span>
                </label>
              </div>
            </div>

            <div className="flex gap-3 mt-4">
              <button type="submit"
                className="px-5 py-2 rounded text-xs font-bold uppercase tracking-wider text-white hover:opacity-90"
                style={{ background: '#FF6B00' }}>
                💾 Save Job
              </button>
              <button type="button" onClick={() => { setShowForm(false); setForm(emptyForm); }}
                className="px-4 py-2 rounded text-xs border font-semibold" style={{ borderColor: '#382E26', color: '#A89F91' }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Quick Reference: Indian Market Times ─────────────────────── */}
      <div className="card p-4">
        <h2 className="text-xs font-bold uppercase tracking-wider mb-3" style={{ color: '#F5EBE1' }}>🇮🇳 Indian Stock Market Timing Reference</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { time: '09:00', label: 'Pre-Market',      color: '#FFAA00', desc: 'Order accumulation' },
            { time: '09:15', label: 'Market Opens',     color: '#00E676', desc: 'NSE/BSE live trading' },
            { time: '12:30', label: 'Mid-Day Scan',     color: '#FF6B00', desc: 'Intraday re-evaluation' },
            { time: '15:15', label: 'Intraday Exit',    color: '#FF8533', desc: 'Auto square-off' },
            { time: '15:30', label: 'Market Closes',    color: '#FF4D4D', desc: 'Regular session ends' },
            { time: '15:40', label: 'After-Market',     color: '#A89F91', desc: 'AMO & post-session' },
          ].map(({ time, label, color, desc }) => (
            <div key={time} className="rounded p-3" style={{ background: '#12100E', borderLeft: `3px solid ${color}`, border: '1px solid #382E26' }}>
              <div className="font-mono font-black text-xs" style={{ color }}>{time} IST</div>
              <div className="font-bold text-xs mt-1" style={{ color: '#F5EBE1' }}>{label}</div>
              <div className="text-[10px] font-mono mt-0.5" style={{ color: '#A89F91' }}>{desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Scheduled Jobs Table ──────────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: '#382E26' }}>
          <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>Configured Jobs ({jobs.length})</h2>
        </div>
        {loading ? (
          <div className="text-center py-10 text-xs font-mono" style={{ color: '#A89F91' }}>Loading jobs…</div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-10 space-y-1">
            <div className="text-3xl">⏱️</div>
            <p className="text-xs font-mono" style={{ color: '#A89F91' }}>No jobs scheduled. Click "+ Create Job" to add one.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#A89F91', background: '#12100E' }}>
                  {['Job / Tickers', 'Type', 'Cron Expression', 'Last Run', 'Status', 'Actions'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold whitespace-nowrap">{h}</th>
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
        <div className="px-4 py-3 border-b flex flex-wrap items-center justify-between gap-2" style={{ borderColor: '#382E26' }}>
          <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: '#F5EBE1' }}>Execution Logs ({logs.length})</h2>
          <div className="flex gap-2 items-center">
            <label className="text-xs font-mono" style={{ color: '#A89F91' }}>Filter Job ID:</label>
            <input type="number" value={logJobId || ''} onChange={e => setLogJobId(e.target.value || null)}
              placeholder="all"
              className="w-20 rounded px-2 py-1 text-xs font-mono outline-none"
              style={{ background: '#12100E', border: '1px solid #382E26', color: '#F5EBE1' }} />
          </div>
        </div>
        {logs.length === 0 ? (
          <div className="text-center py-8 text-xs font-mono" style={{ color: '#A89F91' }}>No execution logs recorded.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: '#A89F91', background: '#12100E' }}>
                  {['Log ID', 'Job ID', 'Status', 'Message', 'Executed At (IST)'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {logs.map(l => (
                  <tr key={l.id} className="table-row-hover border-b" style={{ borderColor: 'rgba(56, 46, 38, 0.4)' }}>
                    <td className="px-3 py-2 font-mono" style={{ color: '#A89F91' }}>#{l.id}</td>
                    <td className="px-3 py-2 font-mono text-[#FF6B00]">#{l.job_id}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${STATUS_COLOR[l.status] || 'badge-orange'}`}>
                        {l.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 max-w-xs truncate font-mono text-xs" style={{ color: '#F5EBE1' }} title={l.message}>
                      {l.message}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap font-mono text-xs" style={{ color: '#A89F91' }}>
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
