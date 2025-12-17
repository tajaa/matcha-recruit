// Company types
export interface Company {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  created_at: string;
  culture_profile: CultureProfile | null;
  interview_count: number;
}

export interface CompanyCreate {
  name: string;
  industry?: string;
  size?: string;
}

export interface CultureProfile {
  collaboration_style: string;
  communication: string;
  pace: string;
  hierarchy: string;
  values: string[];
  work_life_balance: string;
  growth_focus: string;
  decision_making: string;
  remote_policy: string;
  team_size: string;
  key_traits: string[];
  red_flags_for_candidates: string[];
  culture_summary: string;
}

// Interview types
export interface Interview {
  id: string;
  company_id: string;
  interviewer_name: string | null;
  interviewer_role: string | null;
  transcript: string | null;
  raw_culture_data: CultureProfile | null;
  status: 'pending' | 'in_progress' | 'completed';
  created_at: string;
  completed_at: string | null;
}

export interface InterviewCreate {
  company_id: string;
  interviewer_name?: string;
  interviewer_role?: string;
}

export interface InterviewStart {
  interview_id: string;
  websocket_url: string;
}

// Candidate types
export interface Candidate {
  id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  skills: string[] | null;
  experience_years: number | null;
  education: Education[] | null;
  created_at: string;
}

export interface CandidateDetail extends Candidate {
  resume_text: string | null;
  parsed_data: Record<string, unknown> | null;
}

export interface Education {
  degree: string;
  field: string;
  institution: string;
  year: number | null;
}

// Match types
export interface MatchResult {
  id: string;
  company_id: string;
  candidate_id: string;
  candidate_name: string | null;
  match_score: number;
  match_reasoning: string | null;
  culture_fit_breakdown: CultureFitBreakdown | null;
  created_at: string;
}

export interface CultureFitBreakdown {
  collaboration_fit: FitScore;
  pace_fit: FitScore;
  values_alignment: FitScore;
  growth_fit: FitScore;
  work_style_fit: FitScore;
}

export interface FitScore {
  score: number;
  reasoning: string;
}

// WebSocket message types
export interface WSMessage {
  type: 'user' | 'assistant' | 'status' | 'system';
  content: string;
  timestamp: number;
}
