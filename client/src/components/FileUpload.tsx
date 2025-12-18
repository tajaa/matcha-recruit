import { useState, useRef, type DragEvent, type ChangeEvent } from 'react';

interface FileUploadProps {
  accept?: string;
  onUpload: (file: File) => void;
  disabled?: boolean;
  label?: string;
  description?: string;
}

export function FileUpload({
  accept = '.csv,.json',
  onUpload,
  disabled = false,
  label = 'Upload file',
  description = 'Drag and drop or click to upload',
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    if (!disabled) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (disabled) return;

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFile = (file: File) => {
    setFileName(file.name);
    onUpload(file);
  };

  const handleClick = () => {
    if (!disabled) {
      inputRef.current?.click();
    }
  };

  return (
    <div
      onClick={handleClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
        ${isDragging
          ? 'border-matcha-500 bg-matcha-500/10'
          : 'border-zinc-700 hover:border-zinc-600 bg-zinc-900/50'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        disabled={disabled}
        className="hidden"
      />

      <div className="flex flex-col items-center gap-3">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isDragging ? 'bg-matcha-500/20' : 'bg-zinc-800'}`}>
          <svg
            className={`w-6 h-6 ${isDragging ? 'text-matcha-500' : 'text-zinc-400'}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>

        <div>
          <p className="text-zinc-200 font-medium">{label}</p>
          <p className="text-zinc-500 text-sm mt-1">{description}</p>
        </div>

        {fileName && (
          <div className="mt-2 px-3 py-1.5 bg-zinc-800 rounded-lg border border-zinc-700">
            <p className="text-sm text-zinc-300">{fileName}</p>
          </div>
        )}

        <p className="text-xs text-zinc-600 mt-2">
          Accepted: {accept.split(',').join(', ')}
        </p>
      </div>
    </div>
  );
}
