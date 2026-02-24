import { useState } from 'react';
import { offerLetters as offerLettersApi } from '../../api/client';
import type { OfferLetter } from '../../types';

export function useRangeNegotiation(
  offerLetters: OfferLetter[],
  setOfferLetters: (letters: OfferLetter[]) => void,
  selectedLetter: OfferLetter | null,
  setSelectedLetter: (letter: OfferLetter | null) => void
) {
  const [sendRangeEmail, setSendRangeEmail] = useState('');
  const [showSendRangePrompt, setShowSendRangePrompt] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSendRange = async (offerId: string) => {
    if (!sendRangeEmail) return;
    const offer = offerLetters.find(o => o.id === offerId);
    if (!offer?.salary_range_min || !offer?.salary_range_max) return;

    try {
      setIsSubmitting(true);
      const updated = await offerLettersApi.sendRange(offerId, {
        candidate_email: sendRangeEmail,
        salary_range_min: offer.salary_range_min,
        salary_range_max: offer.salary_range_max,
      });
      setOfferLetters(offerLetters.map(o => o.id === offerId ? updated : o));
      if (selectedLetter?.id === offerId) setSelectedLetter(updated);
      setShowSendRangePrompt(null);
      setSendRangeEmail('');
    } catch (error) {
      console.error('Failed to send range offer:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReNegotiate = async (offerId: string) => {
    try {
      setIsSubmitting(true);
      const updated = await offerLettersApi.reNegotiate(offerId);
      setOfferLetters(offerLetters.map(o => o.id === offerId ? updated : o));
      if (selectedLetter?.id === offerId) setSelectedLetter(updated);
    } catch (err) {
      console.error('Re-negotiate failed:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return {
    sendRangeEmail,
    setSendRangeEmail,
    showSendRangePrompt,
    setShowSendRangePrompt,
    isSubmitting,
    handleSendRange,
    handleReNegotiate,
  };
}
