import { useState, useRef, type DragEvent, type ChangeEvent } from 'react';

interface FileUploadProps {
  accept?: string;
  onUpload: (files: File[]) => void;
  disabled?: boolean;
  label?: string;
  description?: string;
  multiple?: boolean;
  allowFolder?: boolean;
}

export function FileUpload({
  accept = '.csv,.json',
  onUpload,
  disabled = false,
  label = 'Upload file',
  description = 'Drag and drop or click to upload',
  multiple = false,
  allowFolder = false,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileNames, setFileNames] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Get accepted extensions for filtering folder contents
  const acceptedExtensions = accept.split(',').map(ext => ext.trim().toLowerCase());

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

    const items = e.dataTransfer.items;
    const files: File[] = [];

    // Handle dropped items (could be files or folders)
    if (items) {
      const filePromises: Promise<File[]>[] = [];

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const entry = item.webkitGetAsEntry?.();
          if (entry) {
            filePromises.push(traverseFileTree(entry));
          } else {
            const file = item.getAsFile();
            if (file) files.push(file);
          }
        }
      }

      if (filePromises.length > 0) {
        Promise.all(filePromises).then(results => {
          const allFiles = results.flat();
          handleFiles(allFiles);
        });
        return;
      }
    }

    // Fallback to regular file list
    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles.length > 0) {
      handleFiles(Array.from(droppedFiles));
    }
  };

  // Recursively traverse directory entries
  const traverseFileTree = (entry: FileSystemEntry): Promise<File[]> => {
    return new Promise((resolve) => {
      if (entry.isFile) {
        (entry as FileSystemFileEntry).file((file) => {
          resolve([file]);
        });
      } else if (entry.isDirectory) {
        const dirReader = (entry as FileSystemDirectoryEntry).createReader();
        dirReader.readEntries((entries) => {
          Promise.all(entries.map(traverseFileTree)).then((results) => {
            resolve(results.flat());
          });
        });
      } else {
        resolve([]);
      }
    });
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFiles(Array.from(files));
    }
  };

  const handleFiles = (files: File[]) => {
    // Filter files by accepted extensions
    const filteredFiles = files.filter(file => {
      const fileName = file.name.toLowerCase();
      return acceptedExtensions.some(ext => fileName.endsWith(ext));
    });

    if (filteredFiles.length === 0) return;

    setFileNames(filteredFiles.map(f => f.name));
    onUpload(filteredFiles);
  };

  const handleFileClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!disabled) {
      fileInputRef.current?.click();
    }
  };

  const handleFolderClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!disabled) {
      folderInputRef.current?.click();
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        relative border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200
        ${isDragging
          ? 'border-white bg-zinc-800'
          : 'border-zinc-700 bg-zinc-900/50'
        }
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        disabled={disabled}
        multiple={multiple}
        className="hidden"
      />
      {allowFolder && (
        <input
          ref={folderInputRef}
          type="file"
          onChange={handleChange}
          disabled={disabled}
          // @ts-expect-error webkitdirectory is not in the type definitions
          webkitdirectory=""
          className="hidden"
        />
      )}

      <div className="flex flex-col items-center gap-3">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isDragging ? 'bg-matcha-500/20' : 'bg-zinc-800'}`}>
          <svg
            className={`w-6 h-6 ${isDragging ? 'text-white' : 'text-zinc-400'}`}
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

        <div className="flex gap-2 mt-2">
          <button
            type="button"
            onClick={handleFileClick}
            disabled={disabled}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Select Files
          </button>
          {allowFolder && (
            <button
              type="button"
              onClick={handleFolderClick}
              disabled={disabled}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Select Folder
            </button>
          )}
        </div>

        {fileNames.length > 0 && (
          <div className="mt-2 px-3 py-1.5 bg-zinc-800 rounded-lg border border-zinc-700">
            <p className="text-sm text-zinc-300">
              {fileNames.length === 1
                ? fileNames[0]
                : `${fileNames.length} files selected`}
            </p>
          </div>
        )}

        <p className="text-xs text-zinc-600 mt-2">
          Accepted: {accept.split(',').join(', ')}
        </p>
      </div>
    </div>
  );
}
