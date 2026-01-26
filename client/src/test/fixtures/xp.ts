import type { VibeCheckConfig, VibeAnalytics, VibeCheckResponse } from '../../types/xp';

export const mockVibeCheckConfig: VibeCheckConfig = {
  id: 'config-1',
  org_id: 'org-1',
  frequency: 'weekly',
  enabled: true,
  is_anonymous: false,
  questions: [],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

export const mockVibeAnalytics: VibeAnalytics = {
  period: 'week',
  total_responses: 25,
  avg_mood_rating: 4.2,
  avg_sentiment_score: 0.65,
  response_rate: 83.3,
  top_themes: [
    { theme: 'workload', count: 8, sentiment: -0.3 },
    { theme: 'team collaboration', count: 6, sentiment: 0.7 },
  ],
  trend_data: [
    { date: '2024-01-20', avg_mood: 3.8 },
    { date: '2024-01-21', avg_mood: 4.1 },
  ],
};

export const mockVibeCheckResponse: VibeCheckResponse = {
  id: 'response-1',
  org_id: 'org-1',
  employee_id: 'emp-1',
  employee_name: 'John Doe',
  mood_rating: 4,
  comment: 'Feeling good',
  sentiment_analysis: {
    score: 0.8,
    themes: ['progress'],
    key_phrases: ['feeling good'],
  },
  created_at: '2024-01-26T10:00:00Z',
};
