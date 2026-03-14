interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
  className?: string;
}

export function ErrorBanner({ message, onDismiss, className = '' }: ErrorBannerProps) {
  return (
    <div className={`border border-zinc-700 rounded px-4 py-3 flex items-center justify-between gap-4 ${className}`}>
      <p className="text-sm text-zinc-300">{message}</p>
      <button onClick={onDismiss} className="text-sm text-zinc-500 hover:text-zinc-300 shrink-0">Dismiss</button>
    </div>
  );
}
