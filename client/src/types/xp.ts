// XP Feature Type Definitions

// Vibe Checks
export interface VibeCheckConfig {
  id: string;
  org_id: string;
  frequency: 'daily' | 'weekly' | 'biweekly' | 'monthly';
  enabled: boolean;
  is_anonymous: boolean;
  questions: Array<{ id: string; text: string; type: string }>;
  created_at: string;
  updated_at: string;
}

export interface VibeAnalytics {
  period: string;
  total_responses: number;
  avg_mood_rating: number;      // 1-5
  avg_sentiment_score: number;  // -1.0 to 1.0
  response_rate: number;         // percentage
  top_themes: Array<{ theme: string; count: number; sentiment: number }>;
  trend_data?: Array<{ date: string; avg_mood: number }>;
}

export interface VibeCheckResponse {
  id: string;
  org_id: string;
  employee_id?: string;
  employee_name?: string;
  mood_rating: number;
  comment?: string;
  custom_responses?: Record<string, any>;
  sentiment_analysis?: {
    score: number;
    themes: string[];
    key_phrases: string[];
  };
  created_at: string;
}

// eNPS Surveys
export interface ENPSSurvey {
  id: string;
  org_id: string;
  title: string;
  description?: string;
  start_date: string;
  end_date: string;
  status: 'draft' | 'active' | 'closed' | 'archived';
  is_anonymous: boolean;
  custom_question?: string;
  created_at: string;
  updated_at: string;
}

export interface ENPSResults {
  enps_score: number;           // -100 to +100
  promoters: number;            // count
  detractors: number;           // count
  passives: number;             // count
  total_responses: number;
  response_rate: number;        // percentage
  promoter_themes: Array<{ theme: string; count: number }>;
  detractor_themes: Array<{ theme: string; count: number }>;
  passive_themes: Array<{ theme: string; count: number }>;
}

export interface ENPSResponse {
  id: string;
  survey_id: string;
  employee_id?: string;
  score: number;                // 0-10
  reason?: string;
  sentiment_analysis?: {
    score: number;
    themes: string[];
  };
  created_at: string;
}

// Performance Reviews
export interface ReviewTemplate {
  id: string;
  org_id: string;
  name: string;
  description?: string;
  categories: Array<{
    id: string;
    name: string;
    weight: number;
    criteria: Array<{
      id: string;
      name: string;
      description: string;
    }>;
  }>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReviewCycle {
  id: string;
  org_id: string;
  title: string;
  description?: string;
  start_date: string;
  end_date: string;
  status: 'draft' | 'active' | 'completed' | 'archived';
  template_id?: string;
  template_name?: string;
  created_at: string;
  updated_at: string;
}

export interface CycleProgress {
  cycle_id: string;
  pending: number;
  self_submitted: number;
  manager_submitted: number;
  completed: number;
  skipped?: number;
  total_reviews: number;
  completion_rate: number;
}

export interface PerformanceReview {
  id: string;
  cycle_id: string;
  cycle_title?: string;
  employee_id: string;
  employee_name?: string;
  manager_id: string;
  manager_name?: string;
  status: 'pending' | 'self_submitted' | 'manager_submitted' | 'completed' | 'skipped';
  self_ratings?: Record<string, number>;
  self_comments?: string;
  self_submitted_at?: string;
  manager_ratings?: Record<string, number>;
  manager_comments?: string;
  manager_overall_rating?: number;
  manager_submitted_at?: string;
  ai_analysis?: {
    alignment_score: number;
    areas_of_agreement: string[];
    discrepancies: Array<{
      category: string;
      self_rating: number;
      manager_rating: number;
      gap: number;
      analysis: string;
    }>;
    strengths: string[];
    development_areas: string[];
    overall_insight: string;
  };
  created_at: string;
  completed_at?: string;
}
