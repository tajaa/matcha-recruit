import { useState, type FormEvent } from 'react';
import { m, AnimatePresence } from 'framer-motion';
import { X, Send, CheckCircle } from 'lucide-react';

interface PricingContactModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PricingContactModal = ({ isOpen, onClose }: PricingContactModalProps) => {
  const [formData, setFormData] = useState({
    companyName: '',
    email: '',
    description: '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const apiBase = import.meta.env.VITE_API_URL || '/api';
      const response = await fetch(`${apiBase}/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: formData.companyName,
          email: formData.email,
          description: formData.description,
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
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-6">
          {/* Backdrop */}
          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          />

          {/* Modal */}
          <m.div
            initial={{ opacity: 0, scale: 0.97, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 16 }}
            transition={{ type: "spring", damping: 28, stiffness: 320 }}
            className="relative w-full max-w-lg bg-zinc-900 border border-white/10 overflow-hidden shadow-2xl"
          >
            {/* Top edge accent */}
            <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-amber-500/60 to-transparent" />

            <button
              onClick={onClose}
              className="absolute top-6 right-6 p-1.5 text-zinc-600 hover:text-white transition-colors"
            >
              <X size={18} />
            </button>

            <div className="p-8 md:p-12">
              {submitted ? (
                <div className="py-10 text-center space-y-6">
                  <m.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", damping: 12, stiffness: 200 }}
                    className="inline-flex items-center justify-center w-16 h-16 border border-amber-500/30 text-amber-500 mb-4"
                  >
                    <CheckCircle size={32} />
                  </m.div>
                  <h3 className="text-xl font-bold text-white uppercase tracking-[0.08em]">Sequence Initiated</h3>
                  <p className="text-zinc-500 text-sm leading-relaxed max-w-xs mx-auto font-light">
                    Your request has been logged. We'll synchronize with you shortly.
                  </p>
                  <button
                    onClick={onClose}
                    className="mt-6 px-10 py-3 bg-white text-zinc-900 text-[10px] font-mono uppercase tracking-[0.3em] font-bold hover:bg-zinc-100 transition-colors"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <div className="mb-10">
                    <p className="text-[10px] font-mono uppercase tracking-[0.4em] text-amber-500 mb-4">Initialize Account // Access</p>
                    <h2 className="text-2xl font-bold text-white tracking-tight uppercase">Request Access</h2>
                    <p className="mt-3 text-zinc-500 text-sm font-light leading-relaxed">
                      Tell us about your organization to receive custom pricing for the Matcha platform.
                    </p>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Company</label>
                      <input
                        type="text"
                        required
                        value={formData.companyName}
                        onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                        className="w-full bg-transparent border-b border-white/10 px-0 py-3 text-sm text-white focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-700"
                        placeholder="Acme Corp"
                      />
                    </div>

                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Email</label>
                      <input
                        type="email"
                        required
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full bg-transparent border-b border-white/10 px-0 py-3 text-sm text-white focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-700"
                        placeholder="name@company.com"
                      />
                    </div>

                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Workforce Scale & Needs</label>
                      <textarea
                        required
                        rows={3}
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        className="w-full bg-transparent border-b border-white/10 px-0 py-3 text-sm text-white focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-700 resize-none"
                        placeholder="Describe your team size and requirements..."
                      />
                    </div>

                    <div className="pt-2">
                      <button
                        type="submit"
                        disabled={isSubmitting}
                        className="group relative w-full py-4 bg-white text-zinc-900 text-[10px] font-mono uppercase tracking-[0.3em] font-bold overflow-hidden disabled:opacity-50"
                      >
                        <span className="relative z-10 flex items-center justify-center gap-3 group-hover:text-white transition-colors duration-500">
                          {isSubmitting ? 'Sending...' : 'Submit Request'}
                          {!isSubmitting && <Send size={11} />}
                        </span>
                        <m.div
                          className="absolute inset-0 bg-zinc-900 border border-white translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]"
                        />
                      </button>
                    </div>
                  </form>
                </>
              )}
            </div>
          </m.div>
        </div>
      )}
    </AnimatePresence>
  );
};
