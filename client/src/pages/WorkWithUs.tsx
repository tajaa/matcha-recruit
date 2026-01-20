import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

export function WorkWithUs() {
  const [formData, setFormData] = useState({
    companyName: '',
    contactName: '',
    email: '',
    description: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';
      const response = await fetch(`${apiBase}/contact`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          company_name: formData.companyName,
          contact_name: formData.contactName,
          email: formData.email,
          description: formData.description,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      setSubmitted(true);
    } catch (error) {
      console.error('Contact form error:', error);
      alert('Failed to send message. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Subtle grid background */}
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
        {/* Radial vignette */}
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
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 border border-zinc-700 px-5 py-2 hover:border-matcha-500 hover:text-matcha-400 transition-all"
          >
            Initialize
          </Link>
        </nav>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-20 max-w-4xl">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16">
          <div className="space-y-8">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
              Work with us
            </h1>
            <p className="text-zinc-400 text-lg leading-relaxed">
              We work selectively with founders and operators who care deeply about fit, culture, and long-term retention.
            </p>
            <p className="text-zinc-400 text-lg leading-relaxed">
              If you are hiring and want to explore working together, you can reach out here.
            </p>
          </div>

          <div className="bg-zinc-900/50 border border-zinc-800 p-8 backdrop-blur-sm">
            {submitted ? (
              <div className="text-center space-y-4 py-8">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-matcha-500/10 text-matcha-500 mb-4">
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h3 className="text-xl font-medium text-white">Message Sent</h3>
                <p className="text-zinc-400">
                  Thank you for your interest. We'll be in touch shortly.
                </p>
                <button
                  onClick={() => setSubmitted(false)}
                  className="mt-4 text-xs tracking-widest uppercase text-matcha-500 hover:text-matcha-400"
                >
                  Send another message
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label htmlFor="companyName" className="block text-[10px] tracking-widest uppercase text-zinc-500 mb-2">
                    Company Name
                  </label>
                  <input
                    type="text"
                    id="companyName"
                    required
                    value={formData.companyName}
                    onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-matcha-500 transition-colors placeholder:text-zinc-700"
                    placeholder="Acme Corp"
                  />
                </div>

                <div>
                  <label htmlFor="contactName" className="block text-[10px] tracking-widest uppercase text-zinc-500 mb-2">
                    Hiring Contact
                  </label>
                  <input
                    type="text"
                    id="contactName"
                    required
                    value={formData.contactName}
                    onChange={(e) => setFormData({ ...formData, contactName: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-matcha-500 transition-colors placeholder:text-zinc-700"
                    placeholder="Jane Doe"
                  />
                </div>

                <div>
                  <label htmlFor="email" className="block text-[10px] tracking-widest uppercase text-zinc-500 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    id="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-matcha-500 transition-colors placeholder:text-zinc-700"
                    placeholder="jane@acme.com"
                  />
                </div>

                <div>
                  <label htmlFor="description" className="block text-[10px] tracking-widest uppercase text-zinc-500 mb-2">
                    How can we help?
                  </label>
                  <textarea
                    id="description"
                    required
                    rows={4}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full bg-zinc-950 border border-zinc-800 px-4 py-3 text-sm text-white focus:outline-none focus:border-matcha-500 transition-colors placeholder:text-zinc-700 resize-none"
                    placeholder="Tell us about your hiring needs..."
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full bg-white text-black text-xs font-medium tracking-widest uppercase py-4 hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? 'Sending...' : 'Start Conversation'}
                </button>
              </form>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default WorkWithUs;
