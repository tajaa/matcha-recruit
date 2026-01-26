import { useState } from 'react';

interface MoodRatingInputProps {
  value: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

const moods = [
  { value: 1, emoji: '😞', label: 'Very Bad', color: 'text-red-400' },
  { value: 2, emoji: '😕', label: 'Bad', color: 'text-orange-400' },
  { value: 3, emoji: '😐', label: 'Okay', color: 'text-amber-400' },
  { value: 4, emoji: '🙂', label: 'Good', color: 'text-emerald-400' },
  { value: 5, emoji: '😄', label: 'Great', color: 'text-emerald-500' },
];

export function MoodRatingInput({ value, onChange, disabled = false }: MoodRatingInputProps) {
  const [hoveredValue, setHoveredValue] = useState<number | null>(null);

  const displayValue = hoveredValue ?? value;
  const selectedMood = moods.find(m => m.value === displayValue);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-center gap-3">
        {moods.map((mood) => (
          <button
            key={mood.value}
            type="button"
            onClick={() => !disabled && onChange(mood.value)}
            onMouseEnter={() => !disabled && setHoveredValue(mood.value)}
            onMouseLeave={() => !disabled && setHoveredValue(null)}
            disabled={disabled}
            className={`
              text-5xl transition-all duration-200
              ${value === mood.value ? 'scale-110' : 'scale-90 opacity-50 hover:opacity-100 hover:scale-100'}
              ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}
            `}
          >
            {mood.emoji}
          </button>
        ))}
      </div>

      {selectedMood && (
        <div className="text-center">
          <span className={`text-sm font-medium ${selectedMood.color}`}>
            {selectedMood.label}
          </span>
        </div>
      )}
    </div>
  );
}
