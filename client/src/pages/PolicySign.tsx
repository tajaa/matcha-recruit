import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckCircle, XCircle, FileText, AlertCircle } from 'lucide-react';

interface SignatureData {
  id: string;
  policy_id: string;
  policy_title: string | null;
  policy_content: string | null;
  policy_file_url: string | null;
  policy_version: string;
  company_name: string | null;
  signer_name: string;
  signer_email: string;
  status: 'pending' | 'signed' | 'declined' | 'expired';
  expires_at: string;
}

const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/api$/, '');

export function PolicySign() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SignatureData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);
  const [declined, setDeclined] = useState(false);

  useEffect(() => {
    if (token) {
      loadSignatureData();
    }
  }, [token]);

  const loadSignatureData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/api/signatures/verify/${token}`);
      if (!res.ok) {
        if (res.status === 404) {
          setError('This signature link is invalid or has expired.');
        } else if (res.status === 410) {
          setError('This document has already been signed or the request was cancelled.');
        } else {
          setError('Failed to load document. Please try again later.');
        }
        return;
      }
      const json = await res.json();
      setData(json);

      if (json.status === 'signed') {
        setSigned(true);
      } else if (json.status === 'declined') {
        setDeclined(true);
      }
    } catch (err) {
      console.error('Failed to load signature data:', err);
      setError('Failed to load document. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSign = async () => {
    if (!token) return;

    try {
      setSigning(true);
      const res = await fetch(`${API_BASE}/api/signatures/verify/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'sign' }),
      });

      if (!res.ok) {
        throw new Error('Failed to sign document');
      }

      setSigned(true);
    } catch (err) {
      console.error('Failed to sign:', err);
      setError('Failed to sign the document. Please try again.');
    } finally {
      setSigning(false);
    }
  };

  const handleDecline = async () => {
    if (!token) return;
    if (!confirm('Are you sure you want to decline this policy? This action cannot be undone.')) {
      return;
    }

    try {
      setSigning(true);
      const res = await fetch(`${API_BASE}/api/signatures/verify/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'decline' }),
      });

      if (!res.ok) {
        throw new Error('Failed to decline document');
      }

      setDeclined(true);
    } catch (err) {
      console.error('Failed to decline:', err);
      setError('Failed to decline the document. Please try again.');
    } finally {
      setSigning(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading document...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="max-w-md text-center">
          <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-6" />
          <h1 className="text-2xl font-bold text-white mb-4">Unable to Load Document</h1>
          <p className="text-zinc-400 mb-8">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest font-bold transition-all"
          >
            Go to Homepage
          </button>
        </div>
      </div>
    );
  }

  if (signed) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="max-w-md text-center">
          <CheckCircle className="w-16 h-16 text-emerald-500 mx-auto mb-6" />
          <h1 className="text-2xl font-bold text-white mb-4">Document Signed</h1>
          <p className="text-zinc-400 mb-2">
            Thank you for signing <span className="text-white font-medium">{data?.policy_title}</span>
          </p>
          <p className="text-zinc-500 text-sm mb-8">
            A confirmation has been sent to {data?.signer_email}
          </p>
          <button
            onClick={() => window.close()}
            className="px-6 py-3 bg-white/10 text-white hover:bg-white/20 text-xs font-mono uppercase tracking-widest transition-all"
          >
            Close Window
          </button>
        </div>
      </div>
    );
  }

  if (declined) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="max-w-md text-center">
          <XCircle className="w-16 h-16 text-zinc-500 mx-auto mb-6" />
          <h1 className="text-2xl font-bold text-white mb-4">Document Declined</h1>
          <p className="text-zinc-400 mb-8">
            You have declined to sign this document. The sender has been notified.
          </p>
          <button
            onClick={() => window.close()}
            className="px-6 py-3 bg-white/10 text-white hover:bg-white/20 text-xs font-mono uppercase tracking-widest transition-all"
          >
            Close Window
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const isExpired = new Date(data.expires_at) < new Date();

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <div className="border-b border-white/10 bg-zinc-900">
        <div className="max-w-4xl mx-auto px-6 py-6">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="w-5 h-5 text-zinc-500" />
            <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">
              Policy Document • v{data.policy_version}
            </span>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">{data.policy_title}</h1>
          <p className="text-sm text-zinc-500 mt-2">From {data.company_name}</p>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="bg-zinc-900 border border-white/10 rounded-sm p-8 mb-8">
          {data.policy_content ? (
            <div className="prose prose-invert prose-zinc max-w-none">
              <div className="text-zinc-300 text-sm leading-relaxed whitespace-pre-wrap font-serif">
                {data.policy_content}
              </div>
            </div>
          ) : data.policy_file_url ? (
            <div className="text-center py-8">
              <FileText className="w-12 h-12 text-zinc-500 mx-auto mb-4" />
              <p className="text-zinc-400 mb-4">This policy is provided as a document.</p>
              <a
                href={data.policy_file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-6 py-3 bg-white/10 text-white hover:bg-white/20 text-xs font-mono uppercase tracking-widest transition-all"
              >
                View Policy Document
              </a>
            </div>
          ) : (
            <p className="text-zinc-500 text-center py-8">No policy content available.</p>
          )}
        </div>

        {/* Signature Section */}
        <div className="bg-zinc-900 border border-white/10 rounded-sm p-8">
          <div className="border-b border-white/10 pb-4 mb-6">
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">Signature Required</h2>
          </div>

          <div className="space-y-4 mb-8">
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Signing as</label>
              <p className="text-white font-medium">{data.signer_name}</p>
              <p className="text-zinc-500 text-sm font-mono">{data.signer_email}</p>
            </div>
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Expires</label>
              <p className={`text-sm ${isExpired ? 'text-red-400' : 'text-zinc-400'}`}>
                {isExpired ? 'EXPIRED' : new Date(data.expires_at).toLocaleDateString(undefined, {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </p>
            </div>
          </div>

          {isExpired ? (
            <div className="bg-red-500/10 border border-red-500/20 rounded-sm p-4 text-center">
              <p className="text-red-400 text-sm">
                This signature request has expired. Please contact the sender to request a new link.
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <button
                onClick={handleSign}
                disabled={signing}
                className="flex-1 px-6 py-4 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <CheckCircle className="w-4 h-4" />
                {signing ? 'Signing...' : 'Sign Document'}
              </button>
              <button
                onClick={handleDecline}
                disabled={signing}
                className="px-6 py-4 bg-transparent border border-white/20 text-zinc-400 hover:text-white hover:border-white/40 text-xs font-mono uppercase tracking-widest transition-all disabled:opacity-50"
              >
                Decline
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-[10px] text-zinc-600 uppercase tracking-wider">
            By signing, you acknowledge that you have read and agree to the terms of this policy.
          </p>
        </div>
      </div>
    </div>
  );
}

export default PolicySign;
