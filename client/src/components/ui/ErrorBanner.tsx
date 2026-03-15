interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
  className?: string;
}

export function ErrorBanner({ message, onDismiss, className = '' }: ErrorBannerProps) {
  return (
    <div className={`bg-stone-200 rounded-lg px-4 py-3 flex items-center justify-between gap-4 ${className}`}>
      <p className="text-sm text-zinc-900">{message}</p>
      <button onClick={onDismiss} className="text-sm text-stone-500 hover:text-zinc-900 shrink-0">Dismiss</button>
    </div>
  );
}
