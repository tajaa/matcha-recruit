import { useState, useEffect } from 'react';
import { offerLetters as offerLettersApi } from '../../api/client';
import type { OfferLetter } from '../../types';

export function useOfferLetters() {
  const [offerLetters, setOfferLetters] = useState<OfferLetter[]>([]);
  const [selectedLetter, setSelectedLetter] = useState<OfferLetter | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadOfferLetters = async () => {
    try {
      setIsLoading(true);
      const data = await offerLettersApi.list();
      setOfferLetters(data);
    } catch (error) {
      console.error('Failed to load offer letters:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadOfferLetters();
  }, []);

  const reload = async () => {
    await loadOfferLetters();
  };

  return {
    offerLetters,
    setOfferLetters,
    selectedLetter,
    setSelectedLetter,
    isLoading,
    reload,
  };
}
