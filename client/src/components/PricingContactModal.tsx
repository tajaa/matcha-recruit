import { useState, type FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, CheckCircle } from 'lucide-react';

interface PricingContactModalProps {
  isOpen: boolean;
  onClose: () => void;
  mode?: 'contact' | 'consultation';
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const TIME_SLOTS = [
  '9:00 AM', '9:30 AM', '10:00 AM', '10:30 AM',
  '11:00 AM', '11:30 AM', '12:00 PM', '12:30 PM',
  '1:00 PM', '1:30 PM', '2:00 PM', '2:30 PM',
  '3:00 PM', '3:30 PM', '4:00 PM', '4:30 PM',
];

function getNextBusinessDays(n: number): Date[] {
  const days: Date[] = [];
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + 1);
  while (days.length < n) {
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) days.push(new Date(d));
    d.setDate(d.getDate() + 1);
  }
  return days;
}

function formatDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const BUSINESS_DAYS = getNextBusinessDays(14);

export function PricingContactModal({ isOpen, onClose, mode = 'contact' }: PricingContactModalProps) {
  const isConsultation = mode === 'consultation';

  const [formData, setFormData] = useState({
    contactName: '',
    companyName: '',
    email: '',
    description: '',
  });
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const apiBase = import.meta.env.VITE_API_URL || '/api';
      const body: Record<string, string> = {
        contact_name: formData.contactName,
        company_name: formData.companyName,
        email: formData.email,
        description: formData.description,
      };
      if (selectedDate) body.preferred_date = selectedDate;
      if (selectedTime) body.preferred_time = selectedTime;

      const response = await fetch(`${apiBase}/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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

  const handleClose = () => {
    onClose();
    setTimeout(() => {
      setSubmitted(false);
      setFormData({ contactName: '', companyName: '', email: '', description: '' });
      setSelectedDate('');
      setSelectedTime('');
    }, 300);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 16 }}
            transition={{ type: 'spring', damping: 28, stiffness: 320 }}
            className="relative w-full max-w-lg bg-zinc-900 border border-white/10 overflow-hidden shadow-2xl max-h-[92vh] flex flex-col"
          >
            <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-amber-500/60 to-transparent" />

            <button
              onClick={handleClose}
              className="absolute top-6 right-6 p-1.5 text-zinc-600 hover:text-white transition-colors z-10"
            >
              <X size={18} />
            </button>

            <div className="overflow-y-auto flex-1 p-8 md:p-12">
              {submitted ? (
                <div className="py-10 text-center space-y-6">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: 'spring', damping: 12, stiffness: 200 }}
                    className="inline-flex items-center justify-center w-16 h-16 border border-amber-500/30 text-amber-500 mb-4"
                  >
                    <CheckCircle size={32} />
                  </motion.div>
                  <h3 className="text-xl font-bold text-white uppercase tracking-[0.08em]">
                    {isConsultation ? 'Consultation Requested' : 'Sequence Initiated'}
                  </h3>
                  <p className="text-zinc-500 text-sm leading-relaxed max-w-xs mx-auto font-light">
                    {isConsultation
                      ? "We'll confirm your time slot within one business day."
                      : "Your request has been logged. We'll synchronize with you shortly."}
                  </p>
                  <button
                    onClick={handleClose}
                    className="mt-6 px-10 py-3 bg-white text-zinc-900 text-[10px] font-mono uppercase tracking-[0.3em] font-bold hover:bg-zinc-100 transition-colors"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <>
                  <div className="mb-8">
                    <p className="text-[10px] font-mono uppercase tracking-[0.4em] text-amber-500 mb-4">
                      {isConsultation ? 'Consulting // Schedule' : 'Initialize Account // Access'}
                    </p>
                    <h2 className="text-2xl font-bold text-white tracking-tight uppercase">
                      {isConsultation ? 'Book a Consultation' : 'Request Access'}
                    </h2>
                    <p className="mt-3 text-zinc-500 text-sm font-light leading-relaxed">
                      {isConsultation
                        ? 'Pick a time and we will confirm within one business day.'
                        : 'Tell us about your organization to receive custom pricing for the Matcha platform.'}
                    </p>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6">
                    {isConsultation && (
                      <>
                        {/* Date picker */}
                        <div>
                          <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-3">
                            Preferred Date
                          </label>
                          <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-none">
                            {BUSINESS_DAYS.map((d) => {
                              const key = formatDateKey(d);
                              const selected = selectedDate === key;
                              return (
                                <button
                                  key={key}
                                  type="button"
                                  onClick={() => { setSelectedDate(key); setSelectedTime(''); }}
                                  className="flex-none flex flex-col items-center gap-1 px-3 py-2.5 text-center transition-colors"
                                  style={{
                                    minWidth: 52,
                                    border: selected ? '1px solid rgba(245,158,11,0.6)' : '1px solid rgba(255,255,255,0.08)',
                                    backgroundColor: selected ? 'rgba(245,158,11,0.08)' : 'transparent',
                                    color: selected ? '#f59e0b' : '#71717a',
                                  }}
                                >
                                  <span className="text-[9px] font-mono uppercase tracking-wider">
                                    {DAY_NAMES[d.getDay()]}
                                  </span>
                                  <span className="text-sm font-medium" style={{ color: selected ? '#f59e0b' : '#e4e4e7' }}>
                                    {d.getDate()}
                                  </span>
                                  <span className="text-[9px]">
                                    {MONTH_NAMES[d.getMonth()]}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        {/* Time slots — only shown once date selected */}
                        {selectedDate && (
                          <motion.div
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2 }}
                          >
                            <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-3">
                              Preferred Time <span className="text-zinc-700 normal-case tracking-normal font-sans">(ET)</span>
                            </label>
                            <div className="grid grid-cols-4 gap-2">
                              {TIME_SLOTS.map((slot) => {
                                const selected = selectedTime === slot;
                                return (
                                  <button
                                    key={slot}
                                    type="button"
                                    onClick={() => setSelectedTime(slot)}
                                    className="py-2 text-[11px] font-mono transition-colors"
                                    style={{
                                      border: selected ? '1px solid rgba(245,158,11,0.6)' : '1px solid rgba(255,255,255,0.08)',
                                      backgroundColor: selected ? 'rgba(245,158,11,0.08)' : 'transparent',
                                      color: selected ? '#f59e0b' : '#a1a1aa',
                                    }}
                                  >
                                    {slot}
                                  </button>
                                );
                              })}
                            </div>
                          </motion.div>
                        )}

                        <div className="border-t border-white/5 pt-2" />
                      </>
                    )}

                    <div>
                      <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">Name</label>
                      <input
                        type="text"
                        required
                        value={formData.contactName}
                        onChange={(e) => setFormData({ ...formData, contactName: e.target.value })}
                        className="w-full bg-transparent border-b border-white/10 px-0 py-3 text-sm text-white focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-700"
                        placeholder="Jane Doe"
                      />
                    </div>

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
                      <label className="block text-[9px] font-mono uppercase tracking-[0.25em] text-zinc-500 mb-2">
                        {isConsultation ? 'What do you need help with?' : 'Workforce Scale & Needs'}
                      </label>
                      <textarea
                        required
                        rows={3}
                        value={formData.description}
                        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                        className="w-full bg-transparent border-b border-white/10 px-0 py-3 text-sm text-white focus:outline-none focus:border-white/40 transition-colors placeholder:text-zinc-700 resize-none"
                        placeholder={isConsultation ? 'Brief description of your situation...' : 'Describe your team size and requirements...'}
                      />
                    </div>

                    <div className="pt-2">
                      <button
                        type="submit"
                        disabled={isSubmitting}
                        className="group relative w-full py-4 bg-white text-zinc-900 text-[10px] font-mono uppercase tracking-[0.3em] font-bold overflow-hidden disabled:opacity-50"
                      >
                        <span className="relative z-10 flex items-center justify-center gap-3 group-hover:text-white transition-colors duration-500">
                          {isSubmitting ? 'Sending...' : isConsultation ? 'Request Consultation' : 'Submit Request'}
                          {!isSubmitting && <Send size={11} />}
                        </span>
                        <motion.div
                          className="absolute inset-0 bg-zinc-900 border border-white translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]"
                        />
                      </button>
                    </div>
                  </form>
                </>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
