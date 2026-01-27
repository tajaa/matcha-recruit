import { Clock, Mail, Building2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface PendingApprovalProps {
  companyName?: string;
  rejectionReason?: string | null;
  status: 'pending' | 'rejected';
}

export function PendingApproval({ companyName, rejectionReason, status }: PendingApprovalProps) {
  const { logout } = useAuth();

  if (status === 'rejected') {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-lg w-full">
          <div className="text-center mb-8">
            <div className="w-16 h-16 mx-auto mb-6 bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <Building2 size={32} className="text-red-400" />
            </div>
            <h1 className="text-3xl font-bold tracking-tighter text-white uppercase mb-2">
              Registration Not Approved
            </h1>
            {companyName && (
              <p className="text-zinc-500 text-sm font-mono">{companyName}</p>
            )}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 p-8 space-y-6">
            <div className="text-center">
              <p className="text-zinc-400 text-sm leading-relaxed">
                We've reviewed your business registration and unfortunately, we're unable to approve it at this time.
              </p>
            </div>

            {rejectionReason && (
              <div className="bg-red-500/5 border border-red-500/20 p-4">
                <div className="text-[10px] uppercase tracking-wider text-red-400 font-bold mb-2">
                  Reason
                </div>
                <p className="text-zinc-300 text-sm">{rejectionReason}</p>
              </div>
            )}

            <div className="bg-zinc-950 border border-zinc-800 p-4">
              <div className="flex items-start gap-3">
                <Mail size={16} className="text-zinc-500 mt-0.5" />
                <div>
                  <p className="text-zinc-400 text-xs">
                    If you believe this was a mistake or have additional information to provide, please contact us at:
                  </p>
                  <a
                    href="mailto:support@hey-matcha.com"
                    className="text-white text-sm font-mono hover:text-emerald-400 transition-colors"
                  >
                    support@hey-matcha.com
                  </a>
                </div>
              </div>
            </div>

            <button
              onClick={() => logout()}
              className="w-full py-3 bg-zinc-800 text-white text-xs uppercase tracking-wider font-bold hover:bg-zinc-700 transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="max-w-lg w-full">
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto mb-6 bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Clock size={32} className="text-amber-400" />
          </div>
          <h1 className="text-3xl font-bold tracking-tighter text-white uppercase mb-2">
            Pending Approval
          </h1>
          {companyName && (
            <p className="text-zinc-500 text-sm font-mono">{companyName}</p>
          )}
        </div>

        <div className="bg-zinc-900 border border-zinc-800 p-8 space-y-6">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs uppercase tracking-wider font-bold mb-4">
              <span className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
              Under Review
            </div>
            <p className="text-zinc-400 text-sm leading-relaxed">
              Your business registration is being reviewed by our team. You'll receive an email notification once it's approved.
            </p>
          </div>

          <div className="border-t border-zinc-800 pt-6">
            <div className="text-[10px] uppercase tracking-wider text-zinc-600 font-bold mb-4">
              What happens next?
            </div>
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs text-zinc-400 font-bold shrink-0">
                  1
                </div>
                <p className="text-zinc-400 text-sm">
                  Our team reviews your registration within 1-2 business days
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs text-zinc-400 font-bold shrink-0">
                  2
                </div>
                <p className="text-zinc-400 text-sm">
                  You'll receive an email when your account is approved
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 bg-zinc-800 border border-zinc-700 flex items-center justify-center text-xs text-zinc-400 font-bold shrink-0">
                  3
                </div>
                <p className="text-zinc-400 text-sm">
                  Once approved, you'll have full access to all Matcha features
                </p>
              </div>
            </div>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 p-4">
            <div className="flex items-start gap-3">
              <Mail size={16} className="text-zinc-500 mt-0.5" />
              <div>
                <p className="text-zinc-400 text-xs">
                  Questions? Contact us at:
                </p>
                <a
                  href="mailto:support@hey-matcha.com"
                  className="text-white text-sm font-mono hover:text-emerald-400 transition-colors"
                >
                  support@hey-matcha.com
                </a>
              </div>
            </div>
          </div>

          <button
            onClick={() => logout()}
            className="w-full py-3 bg-zinc-800 text-white text-xs uppercase tracking-wider font-bold hover:bg-zinc-700 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>
    </div>
  );
}

export default PendingApproval;
