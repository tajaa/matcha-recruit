import { useState, useEffect, useRef } from 'react';
import { Search } from 'lucide-react';

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  debounceMs?: number;
}

export function SearchInput({ value, onChange, placeholder = 'Search...', className = '', debounceMs = 300 }: SearchInputProps) {
  const [local, setLocal] = useState(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setLocal(value); }, [value]);
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onChange(local), debounceMs);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [local, debounceMs]);

  return (
    <div className={`relative flex-1 min-w-[200px] max-w-sm ${className}`}>
      <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
      <input
        type="text"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-8 pr-3 py-2 bg-zinc-900 border border-zinc-800 text-zinc-200 text-sm rounded focus:outline-none focus:border-zinc-600 placeholder:text-zinc-600"
      />
    </div>
  );
}
