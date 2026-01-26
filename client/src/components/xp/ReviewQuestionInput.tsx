import { StarRatingInput } from './StarRatingInput';

interface ReviewQuestionInputProps {
  question: {
    id: string;
    name: string;
    description: string;
  };
  type: 'rating' | 'text';
  value: number | string;
  onChange: (value: number | string) => void;
  disabled?: boolean;
}

export function ReviewQuestionInput({
  question,
  type,
  value,
  onChange,
  disabled = false,
}: ReviewQuestionInputProps) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-white">{question.name}</div>
        {question.description && (
          <div className="text-xs text-zinc-500 mt-1">{question.description}</div>
        )}
      </div>

      {type === 'rating' ? (
        <div className="flex items-center gap-4">
          <StarRatingInput
            value={typeof value === 'number' ? value : 0}
            onChange={(rating) => onChange(rating)}
            disabled={disabled}
            size={24}
          />
          <span className="text-sm text-zinc-400">
            {typeof value === 'number' && value > 0 ? `${value} / 5` : 'Not rated'}
          </span>
        </div>
      ) : (
        <textarea
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="Enter your response..."
          rows={3}
          className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-3 text-sm rounded focus:border-white/30 focus:outline-none resize-none disabled:opacity-50"
        />
      )}
    </div>
  );
}
