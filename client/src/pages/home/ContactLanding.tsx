import { useState, type FormEvent } from 'react';
import { Send, CheckCircle } from 'lucide-react';
import { API_BASE } from '../../api/client';

const BG = '#F5F2ED';
const INK = '#1F1D1A';
const MUTED = '#6B6760';
const LINE = '#E4DED2';
const ACCENT = '#b48228';

export default function ContactLanding() {
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    contactName: '',
    companyName: '',
    email: '',
    description: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [honeypot, setHoneypot] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_name: formData.contactName,
          company_name: formData.companyName,
          email: formData.email,
          description: formData.description,
          website: honeypot,
        }),
      });
      if (!response.ok) throw new Error('Failed to send message');
      setSubmitted(true);
    } catch (error) {
      console.error('Contact form error:', error);
      alert('Failed to send message. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: BG, colorScheme: 'light' }}>
      <nav className="w-full px-6 md:px-12 py-6 flex items-center justify-between">
        <span className="text-sm font-bold uppercase tracking-[0.2em]" style={{ color: INK }}>
          Matcha
        </span>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-[10px] font-mono uppercase tracking-[0.3em] font-bold"
          style={{ color: MUTED }}
        >
          Contact
        </button>
      </nav>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        {!showForm ? (
          <div className="text-center">
            <h1 className="text-4xl md:text-6xl font-bold uppercase tracking-[0.08em]" style={{ color: INK }}>
              Matcha
            </h1>
            <button
              onClick={() => setShowForm(true)}
              className="mt-8 px-10 py-3 text-[10px] font-mono uppercase tracking-[0.3em] font-bold transition-opacity hover:opacity-90"
              style={{ backgroundColor: INK, color: BG }}
            >
              Contact
            </button>
          </div>
        ) : (
        <div
          className="w-full max-w-lg"
          style={{ backgroundColor: BG, border: `1px solid ${LINE}` }}
        >
          <div className="absolute w-full h-px bg-gradient-to-r from-transparent to-transparent" style={{ background: `linear-gradient(to right, transparent, ${ACCENT}66, transparent)` }} />
          <div className="p-8 md:p-12">
            {submitted ? (
              <div className="py-10 text-center space-y-6">
                <div
                  className="inline-flex items-center justify-center w-16 h-16 mb-4"
                  style={{ border: '1px solid rgba(180, 130, 40, 0.4)', color: ACCENT }}
                >
                  <CheckCircle size={32} />
                </div>
                <h3 className="text-xl font-bold uppercase tracking-[0.08em]" style={{ color: INK }}>
                  Message Sent
                </h3>
                <p className="text-sm leading-relaxed max-w-xs mx-auto font-light" style={{ color: MUTED }}>
                  Thanks for reaching out. We'll be in touch shortly.
                </p>
              </div>
            ) : (
              <>
                <div className="mb-8">
                  <p className="text-[10px] font-mono uppercase tracking-[0.4em] mb-4" style={{ color: ACCENT }}>
                    Get In Touch
                  </p>
                  <h2 className="text-2xl font-bold tracking-tight uppercase" style={{ color: INK }}>
                    Contact Us
                  </h2>
                  <p className="mt-3 text-sm font-light leading-relaxed" style={{ color: MUTED }}>
                    Signups are paused right now — send us a message and we'll follow up.
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                  <input
                    type="text"
                    name="website"
                    tabIndex={-1}
                    autoComplete="off"
                    aria-hidden="true"
                    value={honeypot}
                    onChange={(e) => setHoneypot(e.target.value)}
                    style={{ position: 'absolute', left: '-9999px', width: 1, height: 1, opacity: 0 }}
                  />

                  <div>
                    <label className="block text-[9px] font-mono uppercase tracking-[0.25em] mb-2" style={{ color: MUTED }}>
                      Name
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.contactName}
                      onChange={(e) => setFormData({ ...formData, contactName: e.target.value })}
                      className="w-full bg-transparent px-0 py-3 text-sm focus:outline-none transition-colors"
                      style={{ color: INK, borderBottom: `1px solid ${LINE}` }}
                      placeholder="Jane Doe"
                    />
                  </div>

                  <div>
                    <label className="block text-[9px] font-mono uppercase tracking-[0.25em] mb-2" style={{ color: MUTED }}>
                      Company
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.companyName}
                      onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                      className="w-full bg-transparent px-0 py-3 text-sm focus:outline-none transition-colors"
                      style={{ color: INK, borderBottom: `1px solid ${LINE}` }}
                      placeholder="Acme Corp"
                    />
                  </div>

                  <div>
                    <label className="block text-[9px] font-mono uppercase tracking-[0.25em] mb-2" style={{ color: MUTED }}>
                      Email
                    </label>
                    <input
                      type="email"
                      required
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      className="w-full bg-transparent px-0 py-3 text-sm focus:outline-none transition-colors"
                      style={{ color: INK, borderBottom: `1px solid ${LINE}` }}
                      placeholder="name@company.com"
                    />
                  </div>

                  <div>
                    <label className="block text-[9px] font-mono uppercase tracking-[0.25em] mb-2" style={{ color: MUTED }}>
                      Message
                    </label>
                    <textarea
                      required
                      rows={4}
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      className="w-full bg-transparent px-0 py-3 text-sm focus:outline-none transition-colors resize-none"
                      style={{ color: INK, borderBottom: `1px solid ${LINE}` }}
                      placeholder="What can we help with?"
                    />
                  </div>

                  <div className="pt-2">
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full py-4 text-[10px] font-mono uppercase tracking-[0.3em] font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-opacity hover:opacity-90 inline-flex items-center justify-center gap-3"
                      style={{ backgroundColor: INK, color: BG }}
                    >
                      {isSubmitting ? 'Sending...' : 'Send Message'}
                      {!isSubmitting && <Send size={11} />}
                    </button>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
        )}
      </main>
    </div>
  );
}
