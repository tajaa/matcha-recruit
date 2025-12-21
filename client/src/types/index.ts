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
export type InterviewType = 'culture' | 'candidate';

// Conversation Analysis types
export interface CoverageDetail {
  covered: boolean;
  depth: 'deep' | 'shallow' | 'none';
  evidence: string | null;
}

export interface CoverageCompleteness {
  overall_score: number;
  dimensions_covered: string[];
  dimensions_missed: string[];
  coverage_details: Record<string, CoverageDetail>;
}

export interface ResponseAnalysisItem {
  question_summary: string;
  response_quality: 'specific' | 'somewhat_specific' | 'vague';
  actionability: 'high' | 'medium' | 'low';
  notes: string | null;
}

export interface ResponseDepth {
  overall_score: number;
  specific_examples_count: number;
  vague_responses_count: number;
  response_analysis: ResponseAnalysisItem[];
}

export interface MissedOpportunity {
  topic: string;
  suggested_followup: string;
  reason: string;
}

export interface PromptSuggestion {
  category: string;
  current_behavior: string;
  suggested_improvement: string;
  priority: 'high' | 'medium' | 'low';
}

export interface ConversationAnalysis {
  coverage_completeness: CoverageCompleteness;
  response_depth: ResponseDepth;
  missed_opportunities: MissedOpportunity[];
  prompt_improvement_suggestions: PromptSuggestion[];
  interview_summary: string;
  analyzed_at: string;
}

export interface Interview {
  id: string;
  company_id: string;
  interviewer_name: string | null;
  interviewer_role: string | null;
  interview_type: InterviewType;
  transcript: string | null;
  raw_culture_data: CultureProfile | null;
  conversation_analysis: ConversationAnalysis | null;
  status: 'pending' | 'in_progress' | 'completed';
  created_at: string;
  completed_at: string | null;
}

export interface InterviewCreate {
  company_id: string;
  interviewer_name?: string;
  interviewer_role?: string;
  interview_type?: InterviewType;
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

// Position types
export type EmploymentType = 'full-time' | 'part-time' | 'contract' | 'internship' | 'temporary';
export type ExperienceLevel = 'entry' | 'mid' | 'senior' | 'lead' | 'executive';
export type RemotePolicy = 'remote' | 'hybrid' | 'onsite';
export type PositionStatus = 'active' | 'closed' | 'draft';

export interface Position {
  id: string;
  company_id: string;
  company_name: string | null;
  title: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  location: string | null;
  employment_type: EmploymentType | null;
  requirements: string[] | null;
  responsibilities: string[] | null;
  required_skills: string[] | null;
  preferred_skills: string[] | null;
  experience_level: ExperienceLevel | null;
  benefits: string[] | null;
  department: string | null;
  reporting_to: string | null;
  remote_policy: RemotePolicy | null;
  visa_sponsorship: boolean;
  status: PositionStatus;
  created_at: string;
  updated_at: string;
}

export interface PositionCreate {
  company_id: string;
  title: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  location?: string;
  employment_type?: EmploymentType;
  requirements?: string[];
  responsibilities?: string[];
  required_skills?: string[];
  preferred_skills?: string[];
  experience_level?: ExperienceLevel;
  benefits?: string[];
  department?: string;
  reporting_to?: string;
  remote_policy?: RemotePolicy;
  visa_sponsorship?: boolean;
}

export interface PositionUpdate {
  title?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  location?: string;
  employment_type?: EmploymentType;
  requirements?: string[];
  responsibilities?: string[];
  required_skills?: string[];
  preferred_skills?: string[];
  experience_level?: ExperienceLevel;
  benefits?: string[];
  department?: string;
  reporting_to?: string;
  remote_policy?: RemotePolicy;
  visa_sponsorship?: boolean;
  status?: PositionStatus;
}

// Position Match types
export interface PositionMatchResult {
  id: string;
  position_id: string;
  candidate_id: string;
  candidate_name: string | null;
  overall_score: number;
  skills_match_score: number;
  experience_match_score: number;
  culture_fit_score: number;
  match_reasoning: string | null;
  skills_breakdown: SkillsBreakdown | null;
  experience_breakdown: ExperienceBreakdown | null;
  culture_fit_breakdown: PositionCultureFitBreakdown | null;
  created_at: string;
}

export interface SkillsBreakdown {
  score: number;
  matched_required: string[];
  missing_required: string[];
  matched_preferred: string[];
  reasoning: string;
}

export interface ExperienceBreakdown {
  score: number;
  candidate_level: string;
  required_level: string;
  years_relevant: string;
  reasoning: string;
}

export interface PositionCultureFitBreakdown {
  score: number;
  reasoning: string;
  strengths: string[];
  concerns: string[];
}

// Bulk Import types
export interface BulkImportError {
  row: number;
  error: string;
  data: Record<string, unknown> | null;
}

export interface BulkImportResult {
  success_count: number;
  error_count: number;
  errors: BulkImportError[];
  imported_ids: string[];
}

// Job Search types (external jobs via SearchAPI)
export type DatePostedFilter = 'today' | '3days' | 'week' | 'month';
export type JobEmploymentTypeFilter = 'FULLTIME' | 'PARTTIME' | 'CONTRACTOR' | 'INTERN';

export interface JobSearchRequest {
  query: string;
  location?: string;
  next_page_token?: string;
  date_posted?: DatePostedFilter;
  employment_type?: JobEmploymentTypeFilter;
}

export interface JobApplyLink {
  link: string;
  source: string;
}

export interface JobDetectedExtensions {
  posted_at?: string;
  schedule_type?: string;
  salary?: string;
  work_from_home?: boolean;
  health_insurance?: boolean;
  dental_coverage?: boolean;
  paid_time_off?: boolean;
}

export interface JobHighlightSection {
  title: string;
  items: string[];
}

export interface JobListing {
  title: string;
  company_name: string;
  location: string;
  description: string;
  detected_extensions?: JobDetectedExtensions;
  extensions?: string[];
  job_highlights?: JobHighlightSection[];
  apply_links: JobApplyLink[];
  thumbnail?: string;
  job_id?: string;
  sharing_link?: string;
}

export interface JobSearchResponse {
  jobs: JobListing[];
  next_page_token?: string;
  query: string;
  location?: string;
}

// Saved Jobs types
export interface SavedJobCreate {
  job_id?: string;
  title: string;
  company_name: string;
  location?: string;
  description?: string;
  salary?: string;
  schedule_type?: string;
  work_from_home?: boolean;
  posted_at?: string;
  apply_link?: string;
  thumbnail?: string;
  extensions?: string[];
  job_highlights?: JobHighlightSection[];
  apply_links?: JobApplyLink[];
  notes?: string;
}

export interface SavedJob extends SavedJobCreate {
  id: string;
  created_at: string;
}

// Auth types
export type UserRole = 'admin' | 'client' | 'candidate';

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AdminRegister {
  email: string;
  password: string;
  name: string;
}

export interface ClientRegister {
  email: string;
  password: string;
  name: string;
  company_id: string;
  phone?: string;
  job_title?: string;
}

export interface CandidateRegister {
  email: string;
  password: string;
  name: string;
  phone?: string;
}

export interface AdminProfile {
  id: string;
  user_id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface ClientProfile {
  id: string;
  user_id: string;
  company_id: string;
  company_name: string;
  name: string;
  phone: string | null;
  job_title: string | null;
  email: string;
  created_at: string;
}

export interface CandidateAuthProfile {
  id: string;
  user_id: string | null;
  name: string | null;
  email: string | null;
  phone: string | null;
  skills: string[] | null;
  experience_years: number | null;
  created_at: string;
}

export interface CurrentUserResponse {
  user: {
    id: string;
    email: string;
    role: UserRole;
  };
  profile: AdminProfile | ClientProfile | CandidateAuthProfile | null;
}
