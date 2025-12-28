import { useState, type KeyboardEvent } from 'react';

interface SkillsInputProps {
  value: string[];
  onChange: (skills: string[]) => void;
  placeholder?: string;
  label?: string;
  disabled?: boolean;
}

export function SkillsInput({
  value,
  onChange,
  placeholder = 'Type and press Enter to add...',
  label,
  disabled = false,
}: SkillsInputProps) {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      const newSkill = inputValue.trim();
      if (!value.includes(newSkill)) {
        onChange([...value, newSkill]);
      }
      setInputValue('');
    } else if (e.key === 'Backspace' && !inputValue && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const removeSkill = (skillToRemove: string) => {
    if (!disabled) {
      onChange(value.filter(skill => skill !== skillToRemove));
    }
  };

  return (
    <div>
      {label && (
        <label className="block text-sm font-medium text-zinc-400 mb-2">
          {label}
        </label>
      )}
      <div
        className={`
          flex flex-wrap gap-2 p-3 bg-zinc-900 border border-zinc-800 rounded-lg
          focus-within:ring-2 focus-within:ring-white focus-within:border-transparent
          ${disabled ? 'opacity-50' : ''}
        `}
      >
        {value.map(skill => (
          <span
            key={skill}
            className="inline-flex items-center gap-1 px-2.5 py-1 bg-zinc-800 text-zinc-300 rounded-md text-sm border border-zinc-700"
          >
            {skill}
            {!disabled && (
              <button
                type="button"
                onClick={() => removeSkill(skill)}
                className="ml-1 text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={value.length === 0 ? placeholder : ''}
          disabled={disabled}
          className="flex-1 min-w-[120px] bg-transparent text-zinc-100 placeholder-zinc-600 outline-none text-sm"
        />
      </div>
    </div>
  );
}
