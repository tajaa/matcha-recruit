import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Folder, 
  ChevronRight, 
  ArrowLeft, 
  Download, 
  ExternalLink,
  BookOpen,
  Info,
  ShieldCheck,
  Tag,
  Layers
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { adminHandbookReferences } from '../../api/client';
import type { HandbookReference } from '../../types';

interface ReferenceMetadata {
  name: string;
  path: string;
  type: string;
  industry: string;
  highlight: string;
}

interface CategoryMetadata {
  id: string;
  title: string;
  description: string;
  references: ReferenceMetadata[];
}

interface MetadataRoot {
  categories: CategoryMetadata[];
}

export default function IndustryHandbooks() {
  const [items, setItems] = useState<HandbookReference[]>([]);
  const [metadata, setMetadata] = useState<MetadataRoot | null>(null);
  const [currentPath, setCurrentPath] = useState('');
  const [selectedFile, setSelectedFile] = useState<{ name: string, content: string, path: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadMetadata();
  }, []);

  useEffect(() => {
    if (currentPath || selectedFile) {
      loadItems(currentPath);
    }
  }, [currentPath, selectedFile]);

  const loadMetadata = async () => {
    try {
      const { content } = await adminHandbookReferences.getContent('metadata.json');
      setMetadata(JSON.parse(content));
    } catch (err) {
      console.error('Failed to load metadata:', err);
    }
  };

  const loadItems = async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminHandbookReferences.list(path);
      // Filter out metadata.json and hidden files from the raw browser
      setItems(data.filter(i => i.name !== 'metadata.json' && !i.name.startsWith('.')));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items');
    } finally {
      setLoading(false);
    }
  };

  const handleFolderClick = (path: string) => {
    setCurrentPath(path);
    setSelectedFile(null);
  };

  const handleFileClick = async (path: string, extension?: string) => {
    if (extension === '.pdf' || path.endsWith('.pdf')) {
      const url = adminHandbookReferences.getFileUrl(path);
      window.open(url, '_blank');
      return;
    }

    setLoading(true);
    try {
      const { content, name } = await adminHandbookReferences.getContent(path);
      setSelectedFile({ content, name, path });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file content');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    if (selectedFile) {
      setSelectedFile(null);
    } else if (currentPath) {
      const parts = currentPath.split('/');
      parts.pop();
      setCurrentPath(parts.join('/'));
    }
  };

  const renderBreadcrumbs = () => {
    const parts = currentPath.split('/').filter(Boolean);
    return (
      <nav className="flex items-center space-x-2 text-[10px] uppercase tracking-widest text-zinc-500 mb-8">
        <button 
          onClick={() => { setCurrentPath(''); setSelectedFile(null); }}
          className="hover:text-white transition-colors"
        >
          Industry References
        </button>
        {parts.map((part, i) => (
          <React.Fragment key={i}>
            <ChevronRight className="w-3 h-3" />
            <button 
              onClick={() => {
                const newPath = parts.slice(0, i + 1).join('/');
                setCurrentPath(newPath);
                setSelectedFile(null);
              }}
              className="hover:text-white transition-colors"
            >
              {part}
            </button>
          </React.Fragment>
        ))}
        {selectedFile && (
          <>
            <ChevronRight className="w-3 h-3" />
            <span className="text-white font-bold">{selectedFile.name}</span>
          </>
        )}
      </nav>
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-12 pb-24">
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase flex items-center gap-3">
              <BookOpen className="w-8 h-8 text-matcha-500" />
              Industry References
            </h1>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <ShieldCheck size={12} className="text-matcha-500" />
            <p className="text-[10px] text-zinc-500 font-mono tracking-widest uppercase">Master Admin Library</p>
          </div>
        </div>
        {(currentPath !== '' || selectedFile) && (
          <button
            onClick={handleBack}
            className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
        )}
      </div>

      {renderBreadcrumbs()}

      {error && (
        <div className="p-6 bg-red-950/20 border border-red-500/20 rounded-sm">
          <div className="flex items-center gap-3">
            <div className="text-red-500 text-xs font-bold uppercase tracking-widest">Error</div>
          </div>
          <p className="mt-2 text-xs text-red-400 font-mono">{error}</p>
        </div>
      )}

      {selectedFile ? (
        <div className="bg-zinc-950 border border-white/10 rounded-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10 bg-zinc-900/50 flex items-center justify-between">
            <h2 className="text-xs font-bold text-white uppercase tracking-widest">{selectedFile.name}</h2>
            <div className="flex space-x-3">
              <a 
                href={adminHandbookReferences.getFileUrl(selectedFile.path)}
                download
                className="flex items-center px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
              >
                <Download className="w-4 h-4 mr-1.5" />
                Download
              </a>
            </div>
          </div>
          <div className="p-8 prose prose-invert prose-zinc max-w-none">
            {selectedFile.name.endsWith('.md') ? (
              <ReactMarkdown>{selectedFile.content}</ReactMarkdown>
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-xs bg-zinc-900 p-6 rounded-sm border border-white/5 text-zinc-300">
                {selectedFile.content}
              </pre>
            )}
          </div>
        </div>
      ) : currentPath ? (
        <div className="grid grid-cols-1 gap-px bg-white/10 border border-white/10">
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-zinc-950 h-20 p-4">
                <div className="flex items-center space-x-4">
                  <div className="bg-zinc-900 h-10 w-10"></div>
                  <div className="flex-1 space-y-2 py-1">
                    <div className="h-2 bg-zinc-900 rounded w-3/4"></div>
                    <div className="h-2 bg-zinc-900 rounded w-1/2"></div>
                  </div>
                </div>
              </div>
            ))
          ) : (
            items.map((item) => (
              <button
                key={item.path}
                onClick={() => item.type === 'directory' ? handleFolderClick(item.path) : handleFileClick(item.path, item.extension)}
                className="flex items-center p-6 bg-zinc-950 hover:bg-zinc-900 transition-colors text-left group border-b border-white/5 last:border-0"
              >
                <div className={`p-3 rounded-sm mr-6 ${item.type === 'directory' ? 'bg-zinc-900 text-zinc-400' : 'bg-matcha-950/30 text-matcha-500'}`}>
                  {item.type === 'directory' ? (
                    <Folder className="w-5 h-5" />
                  ) : item.extension === '.pdf' ? (
                    <div className="relative">
                      <FileText className="w-5 h-5" />
                      <span className="absolute -bottom-1 -right-1 text-[7px] font-bold bg-red-500 text-white px-0.5 rounded-xs">PDF</span>
                    </div>
                  ) : (
                    <FileText className="w-5 h-5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-white uppercase tracking-tight group-hover:text-zinc-300 transition-colors">
                    {item.name}
                  </p>
                  <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest mt-1">
                    {item.type === 'directory' ? 'Directory' : item.extension?.toUpperCase().replace('.', '') || 'File'}
                  </p>
                </div>
                <ChevronRight className="w-4 h-4 text-zinc-700 group-hover:text-white transition-colors" />
              </button>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-16">
          {metadata?.categories.map((category) => (
            <div key={category.id} className="space-y-6">
              <div className="border-l-2 border-matcha-500 pl-6">
                <h2 className="text-xl font-bold text-white uppercase tracking-tight">{category.title}</h2>
                <p className="text-xs text-zinc-500 mt-1 uppercase tracking-wider">{category.description}</p>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {category.references.map((ref) => (
                  <button
                    key={ref.path}
                    onClick={() => ref.type === 'directory' ? handleFolderClick(ref.path) : handleFileClick(ref.path)}
                    className="flex flex-col p-6 bg-zinc-900/30 border border-white/5 hover:border-matcha-500/50 hover:bg-zinc-900/50 transition-all text-left group relative overflow-hidden"
                  >
                    <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-30 transition-opacity">
                      {ref.type === 'pdf' ? <FileText size={40} /> : <Layers size={40} />}
                    </div>
                    
                    <div className="flex items-center gap-2 mb-4">
                      <Tag size={10} className="text-matcha-500" />
                      <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">{ref.industry}</span>
                    </div>
                    
                    <h3 className="text-sm font-bold text-white uppercase tracking-tight mb-2 group-hover:text-matcha-400 transition-colors">
                      {ref.name}
                    </h3>
                    
                    <p className="text-[10px] text-zinc-400 leading-relaxed font-medium">
                      {ref.highlight}
                    </p>
                    
                    <div className="mt-6 flex items-center gap-2 text-[9px] font-bold text-zinc-600 uppercase tracking-widest group-hover:text-white transition-colors">
                      View Reference
                      <ChevronRight size={10} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
          
          {!metadata && (
            <div className="flex items-center justify-center py-24 border border-dashed border-white/10">
              <p className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 animate-pulse">Initializing Library...</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
