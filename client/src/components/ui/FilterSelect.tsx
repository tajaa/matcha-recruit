interface FilterSelectOption { value: string; label: string; }

interface FilterSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: FilterSelectOption[];
  placeholder?: string;
  className?: string;
}

export function FilterSelect({ value, onChange, options, placeholder = 'All', className = '' }: FilterSelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`px-3 py-2 bg-white border border-stone-300 text-zinc-900 text-sm rounded-lg focus:outline-none focus:border-stone-400 ${className}`}
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
    </select>
  );
}
