interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
  className?: string;
}

export function ErrorBanner({ message, onDismiss, className = '' }: ErrorBannerProps) {
  return (
    <div className={`border border-zinc-300 rounded px-4 py-3 flex items-center justify-between gap-4 bg-zinc-50 ${className}`}>
      <p className="text-sm text-zinc-700">{message}</p>
      <button onClick={onDismiss} className="text-sm text-zinc-400 hover:text-zinc-700 shrink-0">Dismiss</button>
    </div>
  );
}
