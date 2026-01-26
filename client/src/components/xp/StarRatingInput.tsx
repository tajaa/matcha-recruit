import { Star } from 'lucide-react';
import { useState } from 'react';

interface StarRatingInputProps {
  value: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
  size?: number;
}

export function StarRatingInput({ value, onChange, disabled = false, size = 20 }: StarRatingInputProps) {
  const [hoveredValue, setHoveredValue] = useState<number | null>(null);

  const displayValue = hoveredValue ?? value;

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((rating) => (
        <button
          key={rating}
          type="button"
          onClick={() => !disabled && onChange(rating)}
          onMouseEnter={() => !disabled && setHoveredValue(rating)}
          onMouseLeave={() => !disabled && setHoveredValue(null)}
          disabled={disabled}
          className={`transition-all duration-150 ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <Star
            size={size}
            className={`${
              rating <= displayValue
                ? 'fill-amber-400 text-amber-400'
                : 'text-zinc-700'
            } transition-colors`}
          />
        </button>
      ))}
    </div>
  );
}
