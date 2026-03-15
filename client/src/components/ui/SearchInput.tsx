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
      <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
      <input
        type="text"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-8 pr-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm rounded-lg focus:outline-none focus:border-stone-400 placeholder:text-stone-400"
      />
    </div>
  );
}
