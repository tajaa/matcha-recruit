import { getAccessToken } from './client';
import type {
  VibeCheckConfig,
  VibeAnalytics,
  VibeCheckResponse,
  ENPSSurvey,
  ENPSResults,
  ENPSResponse,
  ReviewTemplate,
  ReviewCycle,
  CycleProgress,
  PerformanceReview,
} from '../types/xp';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

// Helper function to make authenticated requests
async function fetchWithAuth(url: string, options: RequestInit = {}) {
  const token = getAccessToken();
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed with status ${response.status}`);
  }

  return response.json();
}

// Vibe Checks API
export const vibeChecksApi = {
  getConfig: async (): Promise<VibeCheckConfig> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/vibe-checks/config`);
  },

  updateConfig: async (config: Partial<VibeCheckConfig>): Promise<VibeCheckConfig> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/vibe-checks/config`, {
      method: 'PATCH',
      body: JSON.stringify(config),
    });
  },

  getAnalytics: async (period: string, managerId?: string): Promise<VibeAnalytics> => {
    const params = new URLSearchParams({ period });
    if (managerId) params.append('manager_id', managerId);
    return fetchWithAuth(`${API_BASE}/v1/xp/vibe-checks/analytics?${params}`);
  },

  getResponses: async (limit = 50, offset = 0, employeeId?: string): Promise<VibeCheckResponse[]> => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (employeeId) params.append('employee_id', employeeId);
    const response = await fetchWithAuth(`${API_BASE}/v1/xp/vibe-checks/responses?${params}`);
    return response.responses || [];
  },

  submitResponse: async (data: { mood_rating: number; comment?: string }): Promise<VibeCheckResponse> => {
    return fetchWithAuth(`${API_BASE}/vibe-checks`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getHistory: async (): Promise<VibeCheckResponse[]> => {
    return fetchWithAuth(`${API_BASE}/vibe-checks/history`);
  },
};

// eNPS API
export const enpsApi = {
  getSurveys: async (status?: string): Promise<ENPSSurvey[]> => {
    const params = status ? `?status=${status}` : '';
    const response = await fetchWithAuth(`${API_BASE}/v1/xp/enps/surveys${params}`);
    return response.surveys || [];
  },

  getSurvey: async (id: string): Promise<ENPSSurvey> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/enps/surveys/${id}`);
  },

  createSurvey: async (survey: Partial<ENPSSurvey>): Promise<ENPSSurvey> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/enps/surveys`, {
      method: 'POST',
      body: JSON.stringify(survey),
    });
  },

  updateSurvey: async (id: string, survey: Partial<ENPSSurvey>): Promise<ENPSSurvey> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/enps/surveys/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(survey),
    });
  },

  getResults: async (id: string): Promise<ENPSResults> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/enps/surveys/${id}/results`);
  },

  getActiveSurveys: async (): Promise<ENPSSurvey[]> => {
    return fetchWithAuth(`${API_BASE}/enps/surveys/active`);
  },

  submitResponse: async (surveyId: string, data: { score: number; reason?: string }): Promise<ENPSResponse> => {
    return fetchWithAuth(`${API_BASE}/enps/surveys/${surveyId}/respond`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

// Performance Reviews API
export const reviewsApi = {
  getTemplates: async (): Promise<ReviewTemplate[]> => {
    const response = await fetchWithAuth(`${API_BASE}/v1/xp/reviews/templates`);
    return response.templates || [];
  },

  getTemplate: async (id: string): Promise<ReviewTemplate> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/templates/${id}`);
  },

  createTemplate: async (template: Partial<ReviewTemplate>): Promise<ReviewTemplate> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/templates`, {
      method: 'POST',
      body: JSON.stringify(template),
    });
  },

  updateTemplate: async (id: string, template: Partial<ReviewTemplate>): Promise<ReviewTemplate> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/templates/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(template),
    });
  },

  getCycles: async (): Promise<ReviewCycle[]> => {
    const response = await fetchWithAuth(`${API_BASE}/v1/xp/reviews/cycles`);
    return response.cycles || [];
  },

  getCycle: async (id: string): Promise<ReviewCycle> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/cycles/${id}`);
  },

  createCycle: async (cycle: Partial<ReviewCycle>): Promise<ReviewCycle> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/cycles`, {
      method: 'POST',
      body: JSON.stringify(cycle),
    });
  },

  updateCycle: async (id: string, cycle: Partial<ReviewCycle>): Promise<ReviewCycle> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/cycles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(cycle),
    });
  },

  getCycleProgress: async (id: string): Promise<CycleProgress> => {
    return fetchWithAuth(`${API_BASE}/v1/xp/reviews/cycles/${id}/progress`);
  },

  getPendingReviews: async (): Promise<PerformanceReview[]> => {
    return fetchWithAuth(`${API_BASE}/reviews/pending`);
  },

  getReview: async (id: string): Promise<PerformanceReview> => {
    return fetchWithAuth(`${API_BASE}/reviews/${id}`);
  },

  submitSelfAssessment: async (id: string, data: { self_ratings: Record<string, number>; self_comments?: string }): Promise<PerformanceReview> => {
    return fetchWithAuth(`${API_BASE}/reviews/${id}/self-assessment`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  submitManagerReview: async (id: string, data: { manager_ratings: Record<string, number>; manager_comments?: string; manager_overall_rating: number }): Promise<PerformanceReview> => {
    return fetchWithAuth(`${API_BASE}/reviews/${id}/manager-review`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
