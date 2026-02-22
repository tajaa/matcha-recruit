import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function PortalUnavailable() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="border border-white/10 bg-zinc-900 p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-3 h-3 bg-white flex items-center justify-center shrink-0">
              <div className="w-1 h-1 bg-black" />
            </div>
            <span className="text-xs tracking-[0.25em] uppercase text-white font-bold">
              Matcha
            </span>
          </div>

          <div className="mb-6">
            <div className="w-8 h-px bg-zinc-600 mb-6" />
            <h1 className="text-sm tracking-[0.2em] uppercase text-white font-bold mb-3">
              Employee Portal Not Available
            </h1>
            <p className="text-xs text-zinc-400 leading-relaxed">
              Your company hasn't activated the Employee Portal. Contact your administrator to enable access.
            </p>
          </div>

          <div className="pt-4 border-t border-white/10">
            <button
              onClick={handleLogout}
              className="text-[10px] tracking-[0.15em] uppercase text-zinc-500 hover:text-white transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
