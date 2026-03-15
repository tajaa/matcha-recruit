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
      className={`px-3 py-2 bg-white border border-zinc-300 text-zinc-800 text-sm rounded focus:outline-none focus:border-zinc-500 ${className}`}
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
    </select>
  );
}
