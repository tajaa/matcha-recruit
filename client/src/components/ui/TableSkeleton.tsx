interface TableSkeletonProps {
  rows?: number;
  className?: string;
}

export function TableSkeleton({ rows = 7, className = '' }: TableSkeletonProps) {
  return (
    <div className={`bg-stone-100 rounded-xl overflow-hidden ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={`flex items-center gap-4 px-4 md:px-6 py-3 ${i > 0 ? 'border-t border-stone-200' : ''}`}
          style={{ opacity: 1 - i * 0.1 }}
        >
          <div className="h-8 w-8 bg-stone-200 animate-pulse rounded-lg shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 bg-stone-200 animate-pulse rounded-md" style={{ width: `${40 + (i % 4) * 12}%` }} />
            <div className="h-3 bg-stone-200/60 animate-pulse rounded-md w-1/4" />
          </div>
          <div className="h-6 w-16 bg-stone-200/60 animate-pulse rounded-full shrink-0" />
          <div className="h-3 w-12 bg-stone-200/60 animate-pulse rounded-md shrink-0" />
        </div>
      ))}
    </div>
  );
}
