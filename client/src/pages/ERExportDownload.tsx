import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { erExportPublic } from '../api/client';
import { Download, Lock, AlertTriangle, FileText } from 'lucide-react';

function ERExportDownload() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<{ filename: string; created_at: string; expired: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [password, setPassword] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    erExportPublic.getInfo(token)
      .then(setInfo)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [token]);

  const handleDownload = async () => {
    if (!token || !password) return;
    setDownloading(true);
    setError(null);
    try {
      const blob = await erExportPublic.download(token, password);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = info?.filename || 'ER-Case-Export.pdf';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Download failed';
      setError(message);
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="animate-pulse text-zinc-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="w-full max-w-sm text-center space-y-4">
          <AlertTriangle size={32} className="mx-auto text-zinc-600" />
          <h1 className="text-zinc-200 text-lg font-semibold">Link Not Found</h1>
          <p className="text-zinc-500 text-sm">This download link is invalid, has been revoked, or does not exist.</p>
        </div>
      </div>
    );
  }

  if (info?.expired) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="w-full max-w-sm text-center space-y-4">
          <AlertTriangle size={32} className="mx-auto text-amber-500" />
          <h1 className="text-zinc-200 text-lg font-semibold">Link Expired</h1>
          <p className="text-zinc-500 text-sm">This download link has expired. Please request a new one from the sender.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 rounded-full">
            <span className="text-[10px] text-zinc-400 uppercase tracking-widest font-bold">Matcha</span>
            <span className="text-[10px] text-zinc-600">|</span>
            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Secure Export</span>
          </div>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-zinc-800 rounded-lg">
              <FileText size={18} className="text-zinc-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-zinc-200 text-sm font-medium truncate">{info?.filename}</p>
              <p className="text-zinc-600 text-[10px] uppercase tracking-wider">
                Created {info?.created_at ? new Date(info.created_at).toLocaleDateString() : ''}
              </p>
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/50 px-3 py-2 rounded-lg border border-red-900/50">
              {error}
            </div>
          )}

          <div>
            <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5 font-bold">Password</label>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter document password"
                className="w-full bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm pl-9 pr-3 py-2.5 rounded-lg placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                onKeyDown={(e) => { if (e.key === 'Enter' && password) handleDownload(); }}
              />
            </div>
          </div>

          <button
            onClick={handleDownload}
            disabled={downloading || !password}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-bold uppercase tracking-wider bg-zinc-100 text-zinc-900 hover:bg-white rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={14} />
            {downloading ? 'Downloading...' : 'Download PDF'}
          </button>
        </div>

        <p className="text-center text-[10px] text-zinc-700">
          Confidential document. Password required.
        </p>
      </div>
    </div>
  );
}

export default ERExportDownload;
