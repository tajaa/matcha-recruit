import { useEffect } from 'react';
import type { ReactNode } from 'react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

export function Modal({ isOpen, onClose, title, children }: ModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto font-mono">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="fixed inset-0 bg-black/90 backdrop-blur-sm transition-opacity"
          onClick={onClose}
        />
        <div className="relative max-w-lg w-full transform transition-all">
          {/* Corner brackets */}
          <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-600" />
          <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-600" />
          <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-600" />
          <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-600" />

          <div className="bg-zinc-900 border border-zinc-800">
            <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
              <h3 className="text-sm tracking-[0.15em] uppercase text-white font-medium">
                {title}
              </h3>
              <button
                onClick={onClose}
                className="text-zinc-600 hover:text-zinc-300 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="px-6 py-5 text-zinc-300">{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
