import { useState } from 'react';
import { offerLetters as offerLettersApi } from '../../api/client';
import type { OfferGuidanceResponse } from '../../types';

const OFFER_GUIDANCE_CITY_STATE: Record<string, string> = {
  'Atlanta': 'GA',
  'Austin': 'TX',
  'Boston': 'MA',
  'Chicago': 'IL',
  'Dallas': 'TX',
  'Denver': 'CO',
  'Los Angeles': 'CA',
  'Miami': 'FL',
  'New York City': 'NY',
  'Philadelphia': 'PA',
  'Phoenix': 'AZ',
  'San Diego': 'CA',
  'San Francisco': 'CA',
  'San Jose': 'CA',
  'Seattle': 'WA',
  'Salt Lake City': 'UT',
  'Washington': 'DC',
};

export const OFFER_GUIDANCE_CITY_OPTIONS = Object.keys(OFFER_GUIDANCE_CITY_STATE);

export function useOfferGuidance() {
  const [guidanceRoleTitle, setGuidanceRoleTitle] = useState('');
  const [guidanceCity, setGuidanceCity] = useState('San Francisco');
  const [guidanceState, setGuidanceState] = useState('CA');
  const [guidanceYearsExperience, setGuidanceYearsExperience] = useState(5);
  const [guidanceEmploymentType, setGuidanceEmploymentType] = useState<string>('Full-Time Exempt');
  const [guidanceLoading, setGuidanceLoading] = useState(false);
  const [guidanceError, setGuidanceError] = useState<string | null>(null);
  const [guidanceResult, setGuidanceResult] = useState<OfferGuidanceResponse | null>(null);

  const handleGuidanceCityChange = (city: string) => {
    setGuidanceCity(city);
    const mappedState = OFFER_GUIDANCE_CITY_STATE[city];
    if (mappedState) {
      setGuidanceState(mappedState);
    }
  };

  const handleGenerateGuidance = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (guidanceLoading) return;

    const trimmedRole = guidanceRoleTitle.trim();
    if (!trimmedRole) {
      setGuidanceError('Role title is required');
      return;
    }

    try {
      setGuidanceLoading(true);
      setGuidanceError(null);
      const result = await offerLettersApi.getPlusRecommendation({
        role_title: trimmedRole,
        city: guidanceCity,
        state: guidanceState,
        years_experience: guidanceYearsExperience,
        employment_type: guidanceEmploymentType,
      });
      setGuidanceResult(result);
    } catch (error) {
      console.error('Failed to generate offer guidance:', error);
      setGuidanceError(error instanceof Error ? error.message : 'Failed to generate guidance');
    } finally {
      setGuidanceLoading(false);
    }
  };

  return {
    guidanceRoleTitle,
    setGuidanceRoleTitle,
    guidanceCity,
    setGuidanceCity,
    guidanceState,
    setGuidanceState,
    guidanceYearsExperience,
    setGuidanceYearsExperience,
    guidanceEmploymentType,
    setGuidanceEmploymentType,
    guidanceLoading,
    guidanceError,
    guidanceResult,
    handleGuidanceCityChange,
    handleGenerateGuidance,
  };
}
