import { useState, useRef, useEffect, useMemo } from 'react';
import usCities from '../data/us-cities.json';

interface CityEntry { city: string; state: string; }
const allCities = usCities as CityEntry[];

interface Props {
  city: string;
  state: string;
  onChange: (city: string, state: string) => void;
  required?: boolean;
  inputClassName?: string;
}

const DEFAULT_INPUT = 'w-full px-3 py-2 bg-zinc-800 border border-zinc-700 text-sm text-white font-mono placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors';

export function CityCombobox({ city, state, onChange, required, inputClassName = DEFAULT_INPUT }: Props) {
  const [query, setQuery] = useState(city ? `${city}, ${state}` : '');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(city ? `${city}, ${state}` : '');
  }, [city, state]);

  const results = useMemo<CityEntry[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q || q.length < 2) return [];
    return allCities.filter(c =>
      c.city.toLowerCase().startsWith(q) ||
      `${c.city.toLowerCase()}, ${c.state.toLowerCase()}`.startsWith(q)
    ).slice(0, 30);
  }, [query]);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, []);

  function handleSelect(entry: CityEntry) {
    onChange(entry.city, entry.state);
    setQuery(`${entry.city}, ${entry.state}`);
    setOpen(false);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setQuery(val);
    setOpen(true);
    if (!val.trim()) onChange('', '');
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        type="text"
        value={query}
        onChange={handleChange}
        onFocus={() => query.trim().length >= 2 && setOpen(true)}
        placeholder="Search city..."
        required={required}
        autoComplete="off"
        className={inputClassName}
      />
      {open && results.length > 0 && (
        <div className="absolute z-50 left-0 right-0 mt-px max-h-44 overflow-y-auto bg-zinc-900 border border-zinc-700 shadow-xl">
          {results.map((entry, i) => (
            <button
              key={i}
              type="button"
              onMouseDown={() => handleSelect(entry)}
              className="w-full text-left px-3 py-1.5 text-xs font-mono text-zinc-400 hover:bg-zinc-800 hover:text-white transition-colors border-b border-zinc-800 last:border-0 flex items-center justify-between"
            >
              <span>{entry.city}</span>
              <span className="text-zinc-600 text-[10px]">{entry.state}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
