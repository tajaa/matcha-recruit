interface NPSRatingInputProps {
  value: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

export function NPSRatingInput({ value, onChange, disabled = false }: NPSRatingInputProps) {
  const getButtonColor = (buttonValue: number, selectedValue: number) => {
    if (selectedValue === -1) return 'bg-zinc-900 text-zinc-400 border-white/10';

    if (buttonValue === selectedValue) {
      if (buttonValue <= 6) return 'bg-red-500 text-white border-red-500';
      if (buttonValue <= 8) return 'bg-amber-500 text-white border-amber-500';
      return 'bg-emerald-500 text-white border-emerald-500';
    }

    return 'bg-zinc-900 text-zinc-400 border-white/10 hover:border-white/30';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-center gap-2 flex-wrap">
        {Array.from({ length: 11 }, (_, i) => i).map((num) => (
          <button
            key={num}
            type="button"
            onClick={() => !disabled && onChange(num)}
            disabled={disabled}
            className={`
              w-12 h-12 border rounded font-bold text-sm
              transition-all duration-200
              ${getButtonColor(num, value)}
              ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
            `}
          >
            {num}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between text-xs text-zinc-500 px-1">
        <span>Not likely at all</span>
        <span>Extremely likely</span>
      </div>

      {value >= 0 && (
        <div className="text-center text-sm">
          <span className="text-zinc-400">
            {value <= 6 && <span className="text-red-400 font-medium">Detractor</span>}
            {value >= 7 && value <= 8 && <span className="text-amber-400 font-medium">Passive</span>}
            {value >= 9 && <span className="text-emerald-400 font-medium">Promoter</span>}
          </span>
        </div>
      )}
    </div>
  );
}
