import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { candidates } from '../api/client';
import { useAuth } from '../context/AuthContext';

type Mode = 'choose' | 'upload' | 'create';

export function ResumeOnboarding() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get('returnTo') || '/app/interviewer';
  const { profile } = useAuth();

  const [mode, setMode] = useState<Mode>('choose');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Create resume form state - pre-fill with profile data
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    skills: '',
    summary: '',
  });

  // Pre-fill form with existing profile data
  useEffect(() => {
    if (profile) {
      setFormData(prev => ({
        ...prev,
        name: profile.name || '',
        phone: 'phone' in profile ? (profile.phone || '') : '',
      }));
    }
  }, [profile]);

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    const ext = file.name.toLowerCase();
    if (!ext.endsWith('.pdf') && !ext.endsWith('.docx') && !ext.endsWith('.doc')) {
      setError('Please upload a PDF or Word document');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File size must be less than 10MB');
      return;
    }
    setError('');
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsLoading(true);
    setError('');

    try {
      await candidates.updateMyResume(selectedFile);
      navigate(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name) {
      setError('Name is required');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      // Use the self-service endpoint that updates the existing candidate record
      await candidates.updateMyProfile({
        name: formData.name,
        phone: formData.phone || undefined,
        skills: formData.skills || undefined,
        summary: formData.summary || undefined,
      });
      navigate(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create profile');
    } finally {
      setIsLoading(false);
    }
  };

  const inputClasses =
    'w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-zinc-700 focus: transition-all';

  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#09090b_70%)]" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse " />
          <span className="text-xs tracking-[0.3em] uppercase text-white font-medium group-hover:text-white transition-colors">
            Matcha
          </span>
        </Link>

        {/* Progress indicator */}
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-matcha-500" />
          <div className="w-8 h-0.5 bg-matcha-500" />
          <div className="w-2 h-2 rounded-full bg-matcha-500" />
          <div className="w-8 h-0.5 bg-zinc-700" />
          <div className="w-2 h-2 rounded-full bg-zinc-700" />
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 flex items-center justify-center min-h-[calc(100vh-140px)] px-4 py-8">
        <div className="w-full max-w-xl">
          {/* Title */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold tracking-[-0.02em] text-white mb-2">
              {mode === 'choose' ? 'ADD YOUR RESUME' : mode === 'upload' ? 'UPLOAD RESUME' : 'CREATE PROFILE'}
            </h1>
            <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
              {mode === 'choose' ? 'Required to continue' : mode === 'upload' ? 'PDF or Word document' : 'Enter your details'}
            </p>
          </div>

          {error && (
            <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide uppercase text-center">
              <span className="text-red-500 mr-2">!</span>
              {error}
            </div>
          )}

          {/* Choose Mode */}
          {mode === 'choose' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Upload Option */}
              <button
                onClick={() => setMode('upload')}
                className="group relative bg-zinc-900/50 border border-zinc-800 p-8 text-center hover:border-zinc-700 transition-all"
              >
                <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700 group-hover:border-zinc-700 transition-colors" />

                <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center group-hover:bg-matcha-500/20 transition-colors">
                  <svg className="w-6 h-6 text-zinc-400 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <h3 className="text-lg font-medium text-white mb-2">Upload Resume</h3>
                <p className="text-xs text-zinc-500">PDF or Word document</p>
              </button>

              {/* Create Option */}
              <button
                onClick={() => setMode('create')}
                className="group relative bg-zinc-900/50 border border-zinc-800 p-8 text-center hover:border-zinc-700 transition-all"
              >
                <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700 group-hover:border-zinc-700 transition-colors" />

                <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-800 flex items-center justify-center group-hover:bg-matcha-500/20 transition-colors">
                  <svg className="w-6 h-6 text-zinc-400 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </div>
                <h3 className="text-lg font-medium text-white mb-2">Create Profile</h3>
                <p className="text-xs text-zinc-500">Enter your details manually</p>
              </button>
            </div>
          )}

          {/* Upload Mode */}
          {mode === 'upload' && (
            <div className="relative">
              <div className="absolute -top-3 -left-3 w-6 h-6 border-t border-l border-zinc-700" />
              <div className="absolute -top-3 -right-3 w-6 h-6 border-t border-r border-zinc-700" />
              <div className="absolute -bottom-3 -left-3 w-6 h-6 border-b border-l border-zinc-700" />
              <div className="absolute -bottom-3 -right-3 w-6 h-6 border-b border-r border-zinc-700" />

              <div className="bg-zinc-900/50 border border-zinc-800 p-8">
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragging(false);
                    handleFileSelect(e.dataTransfer.files);
                  }}
                  className={`relative border-2 border-dashed p-8 text-center transition-all ${
                    isDragging ? 'border-white bg-zinc-800' : 'border-zinc-700'
                  }`}
                >
                  <div className={`w-12 h-12 mx-auto mb-4 rounded-full flex items-center justify-center ${isDragging ? 'bg-matcha-500/20' : 'bg-zinc-800'}`}>
                    <svg className={`w-6 h-6 ${isDragging ? 'text-white' : 'text-zinc-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>

                  {selectedFile ? (
                    <div className="mb-4">
                      <p className="text-white font-medium">{selectedFile.name}</p>
                      <p className="text-xs text-zinc-500 mt-1">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-zinc-300 mb-2">Drag and drop your resume here</p>
                      <p className="text-xs text-zinc-500">or click to browse</p>
                    </>
                  )}

                  <input
                    type="file"
                    accept=".pdf,.docx,.doc"
                    onChange={(e) => handleFileSelect(e.target.files)}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                </div>

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => { setMode('choose'); setSelectedFile(null); setError(''); }}
                    className="flex-1 py-3 border border-zinc-700 text-zinc-400 text-[11px] tracking-[0.2em] uppercase font-medium hover:border-zinc-600 hover:text-zinc-300 transition-all"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleUpload}
                    disabled={!selectedFile || isLoading}
                    className="flex-1 py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                  >
                    {isLoading ? 'Uploading...' : 'Continue'}
                  </button>
                </div>

                <p className="text-[10px] text-zinc-600 text-center mt-4">
                  Accepted: PDF, DOCX, DOC (max 10MB)
                </p>
              </div>
            </div>
          )}

          {/* Create Mode */}
          {mode === 'create' && (
            <div className="relative">
              <div className="absolute -top-3 -left-3 w-6 h-6 border-t border-l border-zinc-700" />
              <div className="absolute -top-3 -right-3 w-6 h-6 border-t border-r border-zinc-700" />
              <div className="absolute -bottom-3 -left-3 w-6 h-6 border-b border-l border-zinc-700" />
              <div className="absolute -bottom-3 -right-3 w-6 h-6 border-b border-r border-zinc-700" />

              <div className="bg-zinc-900/50 border border-zinc-800 p-8">
                <form onSubmit={handleCreateSubmit}>
                  <div className="mb-5">
                    <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                      Full Name *
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      required
                      className={inputClasses}
                      placeholder="Your full name"
                    />
                  </div>

                  <div className="mb-5">
                    <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                      Phone <span className="text-zinc-700">(Optional)</span>
                    </label>
                    <input
                      type="tel"
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      className={inputClasses}
                      placeholder="+1 (555) 123-4567"
                    />
                  </div>

                  <div className="mb-5">
                    <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                      Skills <span className="text-zinc-700">(comma separated)</span>
                    </label>
                    <input
                      type="text"
                      value={formData.skills}
                      onChange={(e) => setFormData({ ...formData, skills: e.target.value })}
                      className={inputClasses}
                      placeholder="JavaScript, Python, Project Management"
                    />
                  </div>

                  <div className="mb-6">
                    <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                      Professional Summary <span className="text-zinc-700">(Optional)</span>
                    </label>
                    <textarea
                      value={formData.summary}
                      onChange={(e) => setFormData({ ...formData, summary: e.target.value })}
                      rows={4}
                      className={`${inputClasses} resize-none`}
                      placeholder="Brief overview of your experience and goals..."
                    />
                  </div>

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => { setMode('choose'); setError(''); }}
                      className="flex-1 py-3 border border-zinc-700 text-zinc-400 text-[11px] tracking-[0.2em] uppercase font-medium hover:border-zinc-600 hover:text-zinc-300 transition-all"
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="flex-1 py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                    >
                      {isLoading ? 'Creating...' : 'Continue'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Status indicator */}
          <div className="mt-8 flex items-center justify-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">
              Step 2 of 3
            </span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="absolute bottom-0 left-0 right-0 z-10 border-t border-zinc-800/50">
        <div className="flex items-center justify-center px-4 sm:px-8 py-4">
          <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-700">
            Matcha Recruit v1.0
          </span>
        </div>
      </footer>
    </div>
  );
}

export default ResumeOnboarding;
