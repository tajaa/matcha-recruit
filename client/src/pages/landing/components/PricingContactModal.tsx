import { useState, type FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
      const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';
      const response = await fetch(`${apiBase}/contact`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          company_name: formData.companyName,
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
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-6">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="relative w-full max-w-lg bg-[#0A0E0C] border border-white/10 rounded-[2rem] overflow-hidden shadow-2xl"
          >
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-[#4ADE80]/50 to-transparent" />
            
            <button
              onClick={onClose}
              className="absolute top-6 right-6 p-2 text-zinc-500 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>

            <div className="p-8 md:p-12">
              {submitted ? (
                <div className="py-12 text-center space-y-6">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", damping: 12, stiffness: 200 }}
                    className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-[#4ADE80]/10 text-[#4ADE80] mb-4"
                  >
                    <CheckCircle size={40} />
                  </motion.div>
                  <h3 className="text-2xl font-bold text-white uppercase tracking-tight">Sequence Initiated</h3>
                  <p className="text-[#F0EFEA]/50 text-sm leading-relaxed max-w-xs mx-auto">
                    Your request for architectural access has been logged. Our systems will synchronize with your endpoint shortly.
                  </p>
                  <button
                    onClick={onClose}
                    className="mt-8 px-10 py-4 bg-white text-black text-[10px] font-mono uppercase tracking-[0.3em] font-bold hover:bg-[#4ADE80] transition-colors rounded-sm"
                  >
                    Close Terminal
                  </button>
                </div>
              ) : (
                <>
                  <div className="mb-10">
                    <h3 className="text-[10px] font-mono uppercase tracking-[0.4em] text-[#4ADE80] mb-4">Architecture Access // Pricing</h3>
                    <h2 className="text-3xl font-bold text-white tracking-tighter uppercase">Request Quote</h2>
                    <p className="mt-4 text-[#F0EFEA]/50 text-sm font-light">
                      Provide your organization telemetry to receive custom pricing for the Matcha operating system.
                    </p>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">Company Entity</label>
                      <input
                        type="text"
                        required
                        value={formData.companyName}
                        onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                        className="w-full bg-white/5 border border-white/10 px-5 py-4 text-sm text-white focus:outline-none focus:border-[#4ADE80]/50 transition-colors rounded-xl placeholder:text-zinc-800"
                        placeholder="e.g. Acme Architecture"
                      />
                    </div>

                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">Endpoint Email</label>
                      <input
                        type="email"
                        required
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        className="w-full bg-white/5 border border-white/10 px-5 py-4 text-sm text-white focus:outline-none focus:border-[#4ADE80]/50 transition-colors rounded-xl placeholder:text-zinc-800"
                        placeholder="name@company.com"
                      />
                    </div>

                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">Operational Scope</label>
                      <textarea
                        required
                        rows={3}
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        className="w-full bg-white/5 border border-white/10 px-5 py-4 text-sm text-white focus:outline-none focus:border-[#4ADE80]/50 transition-colors rounded-xl placeholder:text-zinc-800 resize-none"
                        placeholder="Describe your workforce scale and requirements..."
                      />
                    </div>

                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="group relative w-full py-5 bg-white text-black text-[10px] font-mono uppercase tracking-[0.3em] font-bold overflow-hidden rounded-sm"
                    >
                      <span className="relative z-10 flex items-center justify-center gap-3">
                        {isSubmitting ? 'Processing...' : 'Transmit Request'}
                        {!isSubmitting && <Send size={12} />}
                      </span>
                      <motion.div 
                        className="absolute inset-0 bg-[#4ADE80] translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]"
                      />
                    </button>
                  </form>
                </>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
