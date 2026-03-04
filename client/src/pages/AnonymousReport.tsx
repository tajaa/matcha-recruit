import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { AlertTriangle, CheckCircle, Shield } from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/api$/, '');

export function AnonymousReport() {
  const { token } = useParams<{ token: string }>();
  const [valid, setValid] = useState<boolean | null>(null);
  const [used, setUsed] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  // Honeypot — hidden from real users
  const [honeypot, setHoneypot] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/api/report/${token}`)
      .then((res) => {
        if (res.status === 410) { setUsed(true); setValid(false); }
        else setValid(res.ok);
      })
      .catch(() => setValid(false));
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || submitting) return;
    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/api/report/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          company_name: honeypot || undefined,
        }),
      });

      if (res.status === 429) {
        setError('Too many reports. Please try again later.');
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Submission failed' }));
        setError(data.detail || 'Submission failed');
        return;
      }

      setSubmitted(true);
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Loading
  if (valid === null) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse font-mono">Validating...</div>
      </div>
    );
  }

  // Already used
  if (used) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center space-y-4">
          <AlertTriangle size={32} className="text-orange-400 mx-auto" />
          <h1 className="text-xl font-bold text-white uppercase tracking-wide">Link Already Used</h1>
          <p className="text-sm text-zinc-500">This reporting link has already been used to submit a report. Please contact your administrator for a new link.</p>
        </div>
      </div>
    );
  }

  // Invalid token
  if (!valid) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center space-y-4">
          <AlertTriangle size={32} className="text-red-400 mx-auto" />
          <h1 className="text-xl font-bold text-white uppercase tracking-wide">Invalid Link</h1>
          <p className="text-sm text-zinc-500">This reporting link is no longer active or does not exist.</p>
        </div>
      </div>
    );
  }

  // Submitted
  if (submitted) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center space-y-4">
          <CheckCircle size={32} className="text-emerald-400 mx-auto" />
          <h1 className="text-xl font-bold text-white uppercase tracking-wide">Report Submitted</h1>
          <p className="text-sm text-zinc-500">Your report has been received. Your identity has not been recorded.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="max-w-lg w-full space-y-8">
        {/* Header */}
        <div className="text-center space-y-3">
          <Shield size={28} className="text-zinc-400 mx-auto" />
          <h1 className="text-2xl font-bold text-white uppercase tracking-wide">Anonymous Report</h1>
          <p className="text-xs text-zinc-500 font-mono">Your identity will not be recorded or stored.</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Honeypot — visually hidden */}
          <div aria-hidden="true" style={{ position: 'absolute', left: '-9999px', top: '-9999px' }}>
            <label htmlFor="company_name">Company</label>
            <input
              id="company_name"
              type="text"
              value={honeypot}
              onChange={(e) => setHoneypot(e.target.value)}
              tabIndex={-1}
              autoComplete="off"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-2">
              Subject
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              minLength={3}
              maxLength={255}
              placeholder="Brief summary of the concern"
              className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-600"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-2">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              minLength={10}
              maxLength={10000}
              rows={6}
              placeholder="Describe the incident, concern, or behavior in detail. Include dates, locations, and any other relevant information."
              className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-zinc-600 resize-y"
            />
            <div className="text-right text-[10px] text-zinc-600 mt-1 font-mono">{description.length}/10000</div>
          </div>

          {error && (
            <div className="px-4 py-3 border border-red-500/40 bg-red-950/30 text-red-300 text-xs uppercase tracking-wider font-mono">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || title.trim().length < 3 || description.trim().length < 10}
            className="w-full py-3 bg-white text-black text-xs font-bold uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting...' : 'Submit Report'}
          </button>
        </form>

        <p className="text-center text-[10px] text-zinc-600 font-mono">
          This form does not collect your name, email, or IP address.
        </p>
      </div>
    </div>
  );
}

export default AnonymousReport;
