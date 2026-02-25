import { useState, useRef, type DragEvent, type ChangeEvent } from 'react';
import { Upload, Image as ImageIcon, Loader2 } from 'lucide-react';

interface LogoUploadProps {
  onUpload: (file: File) => Promise<void>;
  currentLogoUrl?: string | null;
  disabled?: boolean;
}

export function LogoUpload({
  onUpload,
  currentLogoUrl,
  disabled = false,
}: LogoUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    if (!disabled && !uploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (disabled || uploading) return;

    const files = Array.from(e.dataTransfer.files);
    const imageFile = files.find(f => f.type.startsWith('image/'));
    
    if (imageFile) {
      await processUpload(imageFile);
    }
  };

  const handleChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const imageFile = files[0];
      if (imageFile.type.startsWith('image/')) {
        await processUpload(imageFile);
      }
    }
  };

  const processUpload = async (file: File) => {
    try {
      setUploading(true);
      await onUpload(file);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleClick = () => {
    if (!disabled && !uploading) {
      fileInputRef.current?.click();
    }
  };

  return (
    <div className="mt-4">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold mb-2">Company Logo</p>
      
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
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
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleChange}
          disabled={disabled || uploading}
          className="hidden"
        />

        {uploading ? (
          <div className="flex flex-col items-center gap-2 py-2">
            <Loader2 className="w-6 h-6 text-matcha-500 animate-spin" />
            <p className="text-xs text-zinc-400 font-mono">Uploading logo...</p>
          </div>
        ) : currentLogoUrl ? (
          <div className="flex flex-col items-center gap-3">
            <div className="relative group/logo">
              <img
                src={currentLogoUrl}
                alt="Current Logo"
                className="max-h-16 max-w-[200px] object-contain rounded"
              />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/logo:opacity-100 transition-opacity flex items-center justify-center rounded">
                <Upload className="w-5 h-5 text-white" />
              </div>
            </div>
            <p className="text-[10px] text-zinc-500 font-mono">Click or drag to replace logo</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-2">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${isDragging ? 'bg-matcha-500/20' : 'bg-zinc-800'}`}>
              <ImageIcon className={`w-5 h-5 ${isDragging ? 'text-matcha-400' : 'text-zinc-500'}`} />
            </div>
            <div>
              <p className="text-xs text-zinc-300 font-medium">Drop company logo here</p>
              <p className="text-[10px] text-zinc-500 mt-1 font-mono tracking-tight">PNG, JPG or SVG (max 5MB)</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
