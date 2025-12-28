import { useState, useEffect, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { publicJobs } from '../api/client';
import type { PublicJobDetail } from '../types';

export function PublicJobApply() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [job, setJob] = useState<PublicJobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Form state
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [coverLetter, setCoverLetter] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    if (jobId) {
      loadJob();
    }
  }, [jobId]);

  const loadJob = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await publicJobs.getDetail(jobId!);
      setJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job');
    } finally {
      setLoading(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      validateAndSetFile(files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      validateAndSetFile(files[0]);
    }
  };

  const validateAndSetFile = (file: File) => {
    const validTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword',
    ];
    const validExtensions = ['.pdf', '.docx', '.doc'];

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!validTypes.includes(file.type) && !validExtensions.includes(ext)) {
      setError('Please upload a PDF or DOCX file');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError('File size must be less than 10MB');
      return;
    }

    setError(null);
    setResumeFile(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!resumeFile) {
      setError('Please upload your resume');
      return;
    }

    if (!name.trim() || !email.trim()) {
      setError('Please fill in all required fields');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      await publicJobs.apply(jobId!, {
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        cover_letter: coverLetter.trim() || undefined,
        source: 'direct',
        resume: resumeFile,
      });

      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit application');
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black flex items-center justify-center">
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

        <div className="relative z-10 text-center px-4 max-w-lg">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-matcha-500/20 flex items-center justify-center">
            <span className="text-3xl text-matcha-500">&#10003;</span>
          </div>
          <h1 className="text-2xl font-bold text-white mb-4">Application Submitted!</h1>
          <p className="text-zinc-400 mb-8">
            Thank you for applying{job ? ` for ${job.title} at ${job.company_name}` : ''}.
            We'll review your application and get back to you soon.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/careers"
              className="px-8 py-3 text-xs font-medium tracking-widest uppercase border border-zinc-700 text-zinc-300 hover:border-matcha-500 hover:text-matcha-400 transition-all"
            >
              View More Jobs
            </Link>
            <Link
              to="/"
              className="px-8 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
            >
              Back to Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

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
          <div className="w-2 h-2 rounded-full bg-matcha-500 shadow-[0_0_10px_rgba(34,197,94,0.8)] group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/careers"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            All Jobs
          </Link>
        </nav>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-12 max-w-2xl">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-6 h-6 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : !job ? (
          <div className="text-center py-20">
            <p className="text-red-400">Job not found</p>
            <button
              onClick={() => navigate('/careers')}
              className="mt-4 text-sm text-matcha-500 hover:text-matcha-400"
            >
              Back to all jobs
            </button>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Back link */}
            <Link
              to={`/careers/${job.id}`}
              className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-matcha-400 transition-colors"
            >
              <span>&larr;</span>
              <span>Back to job details</span>
            </Link>

            {/* Job Info */}
            <div className="border border-zinc-800 bg-zinc-900/30 p-6">
              <p className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Applying for
              </p>
              <h1 className="text-xl font-bold text-white">{job.title}</h1>
              <p className="text-zinc-400">{job.company_name}</p>
            </div>

            {/* Application Form */}
            <form onSubmit={handleSubmit} className="space-y-6">
              <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                Your Information
              </h2>

              {/* Name */}
              <div>
                <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full bg-zinc-900/50 border border-zinc-800 px-4 py-3 text-white placeholder-zinc-600 focus:border-matcha-500 focus:outline-none transition-colors"
                  placeholder="John Doe"
                />
              </div>

              {/* Email */}
              <div>
                <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full bg-zinc-900/50 border border-zinc-800 px-4 py-3 text-white placeholder-zinc-600 focus:border-matcha-500 focus:outline-none transition-colors"
                  placeholder="john@example.com"
                />
              </div>

              {/* Phone */}
              <div>
                <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Phone (optional)
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full bg-zinc-900/50 border border-zinc-800 px-4 py-3 text-white placeholder-zinc-600 focus:border-matcha-500 focus:outline-none transition-colors"
                  placeholder="+1 (555) 123-4567"
                />
              </div>

              {/* Resume Upload */}
              <div>
                <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Resume <span className="text-red-500">*</span>
                </label>
                <div
                  className={`border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
                    dragActive
                      ? 'border-matcha-500 bg-matcha-500/10'
                      : resumeFile
                      ? 'border-matcha-500/50 bg-zinc-900/50'
                      : 'border-zinc-700 bg-zinc-900/30 hover:border-zinc-600'
                  }`}
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.doc"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {resumeFile ? (
                    <div>
                      <p className="text-matcha-400 font-medium">{resumeFile.name}</p>
                      <p className="text-zinc-500 text-sm mt-1">
                        {(resumeFile.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setResumeFile(null);
                        }}
                        className="mt-2 text-sm text-red-400 hover:text-red-300"
                      >
                        Remove
                      </button>
                    </div>
                  ) : (
                    <div>
                      <p className="text-zinc-400">
                        Drag and drop your resume here, or{' '}
                        <span className="text-matcha-500">browse</span>
                      </p>
                      <p className="text-zinc-600 text-sm mt-2">PDF or DOCX, max 10MB</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Cover Letter */}
              <div>
                <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                  Cover Letter (optional)
                </label>
                <textarea
                  value={coverLetter}
                  onChange={(e) => setCoverLetter(e.target.value)}
                  rows={6}
                  className="w-full bg-zinc-900/50 border border-zinc-800 px-4 py-3 text-white placeholder-zinc-600 focus:border-matcha-500 focus:outline-none transition-colors resize-none"
                  placeholder="Tell us why you're interested in this role..."
                />
              </div>

              {/* Error */}
              {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  {error}
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={submitting || !resumeFile}
                className="w-full py-4 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
                    Submitting...
                  </span>
                ) : (
                  'Submit Application'
                )}
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
}

export default PublicJobApply;
