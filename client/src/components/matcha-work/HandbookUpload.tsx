import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { FileText, Loader2, Upload } from 'lucide-react';

interface HandbookUploadProps {
  onUpload: (file: File) => Promise<void>;
  currentFilename?: string | null;
  disabled?: boolean;
}

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.doc'];

function isSupportedHandbookFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function HandbookUpload({
  onUpload,
  currentFilename,
  disabled = false,
}: HandbookUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  const processUpload = async (file: File) => {
    if (!isSupportedHandbookFile(file)) return;
    try {
      setUploading(true);
      await onUpload(file);
    } finally {
      setUploading(false);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  };

  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0];
    if (nextFile) {
      await processUpload(nextFile);
    }
  };

  const handleDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (disabled || uploading) return;

    const nextFile = Array.from(event.dataTransfer.files).find(isSupportedHandbookFile);
    if (nextFile) {
      await processUpload(nextFile);
    }
  };

  const handleClick = () => {
    if (!disabled && !uploading) {
      inputRef.current?.click();
    }
  };

  return (
    <div className="mt-4">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-2">Upload Existing Handbook</p>

      <div
        onClick={handleClick}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !uploading) {
            setIsDragging(true);
          }
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setIsDragging(false);
        }}
        onDrop={handleDrop}
        className={`
          relative border-2 border-dashed rounded-xl p-4 text-center transition-all duration-200 cursor-pointer
          ${isDragging
            ? 'border-matcha-500 bg-matcha-500/5'
            : 'border-zinc-700 bg-zinc-900/30 hover:border-zinc-600 hover:bg-zinc-800/50'
          }
          ${disabled || uploading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.doc,.docx"
          onChange={handleChange}
          disabled={disabled || uploading}
          className="hidden"
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-2 py-2">
            <Loader2 className="w-6 h-6 text-matcha-500 animate-spin" />
            <p className="text-xs text-zinc-400 font-mono">Uploading handbook...</p>
          </div>
        ) : currentFilename ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-zinc-800 flex items-center justify-center">
              <FileText className="w-5 h-5 text-zinc-300" />
            </div>
            <div>
              <p className="text-xs text-zinc-200 font-medium">{currentFilename}</p>
              <p className="text-[10px] text-zinc-500 mt-1 font-mono tracking-tight">Click or drag to replace the uploaded handbook</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-2">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${isDragging ? 'bg-matcha-500/20' : 'bg-zinc-800'}`}>
              {isDragging ? <Upload className="w-5 h-5 text-matcha-400" /> : <FileText className="w-5 h-5 text-zinc-500" />}
            </div>
            <div>
              <p className="text-xs text-zinc-300 font-medium">Drop handbook file here</p>
              <p className="text-[10px] text-zinc-500 mt-1 font-mono tracking-tight">PDF, DOCX, or DOC (max 10MB)</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
