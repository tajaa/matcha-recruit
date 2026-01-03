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
export type InterviewType = 'culture' | 'candidate' | 'screening';

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
  response_quality: 'specific' | 'somewhat_specific' | 'vague' | 'shallow';
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

// Screening Analysis types
export interface ScreeningAttribute {
  score: number;
  evidence: string[];
  notes: string | null;
}

export interface ScreeningAnalysis {
  communication_clarity: ScreeningAttribute;
  engagement_energy: ScreeningAttribute;
  critical_thinking: ScreeningAttribute;
  professionalism: ScreeningAttribute;
  overall_score: number;
  recommendation: 'strong_pass' | 'pass' | 'borderline' | 'fail';
  summary: string;
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
  screening_analysis: ScreeningAnalysis | null;
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
  show_on_job_board: boolean;
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
  row?: number;
  file?: string;
  error: string;
  data?: Record<string, unknown> | null;
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
    beta_features?: Record<string, boolean>;
    interview_prep_tokens?: number;
    allowed_interview_roles?: string[];
  };
  profile: AdminProfile | ClientProfile | CandidateAuthProfile | null;
}

// Beta access management types
export interface CandidateBetaInfo {
  user_id: string;
  email: string;
  name: string | null;
  beta_features: Record<string, boolean>;
  interview_prep_tokens: number;
  allowed_interview_roles: string[];
  total_sessions: number;
  avg_score: number | null;
  last_session_at: string | null;
}

export interface CandidateBetaListResponse {
  candidates: CandidateBetaInfo[];
  total: number;
}

export interface CandidateSessionSummary {
  session_id: string;
  interview_role: string | null;
  duration_minutes: number;
  status: string;
  created_at: string;
  response_quality_score: number | null;
  communication_score: number | null;
}

// Project types
export type ProjectStatus = 'draft' | 'active' | 'completed' | 'cancelled';
export type CandidateStage = 'initial' | 'screening' | 'interview' | 'finalist' | 'placed' | 'rejected';

export interface Project {
  id: string;
  company_name: string;
  name: string;
  position_title: string | null;
  location: string | null;
  salary_min: number | null;
  salary_max: number | null;
  benefits: string | null;
  requirements: string | null;
  status: ProjectStatus;
  notes: string | null;
  candidate_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  company_name: string;
  name: string;
  position_title?: string;
  location?: string;
  salary_min?: number;
  salary_max?: number;
  benefits?: string;
  requirements?: string;
  status?: ProjectStatus;
  notes?: string;
}

export interface ProjectUpdate {
  company_name?: string;
  name?: string;
  position_title?: string;
  location?: string;
  salary_min?: number;
  salary_max?: number;
  benefits?: string;
  requirements?: string;
  status?: ProjectStatus;
  notes?: string;
}

export interface ProjectCandidate {
  id: string;
  project_id: string;
  candidate_id: string;
  candidate_name: string | null;
  candidate_email: string | null;
  candidate_phone: string | null;
  candidate_skills: string[];
  candidate_experience_years: number | null;
  stage: CandidateStage;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCandidateAdd {
  candidate_id: string;
  stage?: CandidateStage;
  notes?: string;
}

export interface ProjectCandidateBulkAdd {
  candidate_ids: string[];
  stage?: CandidateStage;
}

export interface ProjectCandidateUpdate {
  stage?: CandidateStage;
  notes?: string;
}

export interface ProjectStats {
  initial: number;
  screening: number;
  interview: number;
  finalist: number;
  placed: number;
  rejected: number;
  total: number;
}

// Outreach types
export type OutreachStatus = 'sent' | 'opened' | 'interested' | 'declined' | 'screening_started' | 'screening_complete' | 'email_failed';

export interface Outreach {
  id: string;
  project_id: string;
  candidate_id: string;
  candidate_name: string | null;
  candidate_email: string | null;
  token: string;
  status: OutreachStatus;
  email_sent_at: string | null;
  interest_response_at: string | null;
  interview_id: string | null;
  screening_score: number | null;
  screening_recommendation: string | null;
  created_at: string;
}

export interface OutreachSendRequest {
  candidate_ids: string[];
  custom_message?: string;
}

export interface OutreachSendResult {
  sent_count: number;
  failed_count: number;
  skipped_count: number;
  errors: { candidate_id?: string; error: string }[];
}

export interface OutreachPublicInfo {
  company_name: string;
  position_title: string | null;
  location: string | null;
  salary_range: string | null;
  requirements: string | null;
  benefits: string | null;
  status: string;
  candidate_name: string | null;
}

export interface OutreachInterestResponse {
  status: string;
  message: string;
  interview_url: string | null;
}

export interface OutreachInterviewStart {
  interview_id: string;
  websocket_url: string;
}

export interface ScreeningPublicInfo {
  company_name: string;
  position_title: string | null;
  location: string | null;
  salary_range: string | null;
  requirements: string | null;
  benefits: string | null;
  status: string;
  candidate_name: string | null;
  candidate_email: string | null;
  interview_id: string | null;
}

// Public Job Board types
export interface PublicJobListing {
  id: string;
  title: string;
  company_name: string;
  location: string | null;
  employment_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  remote_policy: string | null;
  created_at: string;
}

export interface PublicJobDetail {
  id: string;
  title: string;
  company_name: string;
  company_id: string;
  location: string | null;
  employment_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  requirements: string[] | null;
  responsibilities: string[] | null;
  required_skills: string[] | null;
  preferred_skills: string[] | null;
  experience_level: string | null;
  benefits: string[] | null;
  department: string | null;
  remote_policy: string | null;
  visa_sponsorship: boolean;
  created_at: string;
  json_ld: Record<string, unknown>;
}

export interface JobListResponse {
  jobs: PublicJobListing[];
  total: number;
}

export interface ApplicationSubmitResponse {
  success: boolean;
  message: string;
  application_id: string;
}

// Tutor Analysis types
export type TutorInterviewType = 'tutor_interview' | 'tutor_language';

// Tutor Interview Analysis (for interview prep mode)
export interface TutorResponseBreakdown {
  question: string;
  quality: 'specific' | 'somewhat_specific' | 'vague';
  used_examples: boolean;
  depth: 'excellent' | 'good' | 'shallow';
  feedback: string;
}

export interface TutorResponseQuality {
  overall_score: number;
  specificity_score: number;
  example_usage_score: number;
  depth_score: number;
  breakdown: TutorResponseBreakdown[];
}

export interface TutorCommunicationSkills {
  overall_score: number;
  clarity_score: number;
  confidence_score: number;
  professionalism_score: number;
  engagement_score: number;
  notes: string | null;
}

export interface TutorMissedOpportunity {
  topic: string;
  suggestion: string;
}

export interface TutorContentCoverage {
  topics_covered: string[];
  missed_opportunities: TutorMissedOpportunity[];
  follow_up_depth: 'excellent' | 'good' | 'shallow';
}

export interface TutorImprovementSuggestion {
  area: string;
  suggestion: string;
  priority: 'high' | 'medium' | 'low';
}

export interface TutorInterviewAnalysis {
  response_quality: TutorResponseQuality;
  communication_skills: TutorCommunicationSkills;
  content_coverage: TutorContentCoverage;
  improvement_suggestions: TutorImprovementSuggestion[];
  session_summary: string;
  analyzed_at: string;
}

// Tutor Language Analysis (for language test mode)
export interface TutorFluencyPace {
  overall_score: number;
  speaking_speed: 'natural' | 'too_fast' | 'too_slow' | 'varies';
  pause_frequency: 'rare' | 'occasional' | 'frequent';
  filler_word_count: number;
  filler_words_used: string[];
  flow_rating: 'excellent' | 'good' | 'choppy' | 'poor';
  notes: string | null;
}

export interface TutorVocabulary {
  overall_score: number;
  variety_score: number;
  appropriateness_score: number;
  complexity_level: 'basic' | 'intermediate' | 'advanced';
  notable_good_usage: string[];
  suggestions: string[];
}

export interface TutorGrammarError {
  error: string;
  correction: string;
  type: string;
}

export interface TutorGrammar {
  overall_score: number;
  sentence_structure_score: number;
  tense_usage_score: number;
  common_errors: TutorGrammarError[];
  notes: string | null;
}

export interface TutorProficiencyLevel {
  level: 'A1' | 'A2' | 'B1' | 'B2' | 'C1' | 'C2';
  level_description: string;
  strengths: string[];
  areas_to_improve: string[];
}

export interface TutorPracticeSuggestion {
  skill: string;
  exercise: string;
  priority: 'high' | 'medium' | 'low';
}

// Spanish-specific analysis types
export interface SpanishConjugationError {
  verb: string;
  user_said: string;
  correct: string;
  tense: string;
  person: string;
}

export interface SpanishConjugation {
  score: number;
  regular_verb_accuracy: number;
  irregular_verb_accuracy: number;
  tense_appropriateness: number;
  subjunctive_attempts: number;
  subjunctive_accuracy: number | null;
  notable_errors: SpanishConjugationError[];
  notes: string;
}

export interface SpanishGenderError {
  phrase: string;
  correction: string;
  rule: string;
}

export interface SpanishGenderAgreement {
  score: number;
  errors: SpanishGenderError[];
  notes: string;
}

export interface SpanishSerEstarError {
  user_said: string;
  correction: string;
  explanation: string;
}

export interface SpanishSerEstar {
  score: number;
  errors: SpanishSerEstarError[];
  notes: string;
}

export interface SpanishPorParaError {
  user_said: string;
  correction: string;
  explanation: string;
}

export interface SpanishPorPara {
  score: number;
  errors: SpanishPorParaError[];
  notes: string;
}

export interface SpanishSpecificAnalysis {
  conjugation: SpanishConjugation;
  gender_agreement: SpanishGenderAgreement;
  ser_estar: SpanishSerEstar;
  por_para: SpanishPorPara;
}

export interface TutorLanguageAnalysis {
  fluency_pace: TutorFluencyPace;
  vocabulary: TutorVocabulary;
  grammar: TutorGrammar;
  overall_proficiency: TutorProficiencyLevel;
  practice_suggestions: TutorPracticeSuggestion[];
  session_summary: string;
  analyzed_at: string;
  language: string;
  spanish_specific?: SpanishSpecificAnalysis;
}

// Tutor Session types
export interface TutorSessionSummary {
  id: string;
  interview_type: TutorInterviewType;
  language: string | null;
  status: string;
  overall_score: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface TutorSessionDetail {
  id: string;
  interview_type: TutorInterviewType;
  language: string | null;
  transcript: string | null;
  tutor_analysis: TutorInterviewAnalysis | TutorLanguageAnalysis | null;
  status: string;
  created_at: string;
  completed_at: string | null;
}

// Tutor Metrics Aggregate types
export interface TutorInterviewPrepStats {
  total_sessions: number;
  avg_response_quality: number;
  avg_communication_score: number;
  common_improvement_areas: { area: string; count: number }[];
}

export interface TutorLanguageTestStats {
  total_sessions: number;
  by_language: Record<string, { count: number; avg_proficiency: string | null }>;
  avg_fluency_score: number;
  avg_grammar_score: number;
  common_grammar_errors: { type: string; count: number }[];
}

export interface TutorMetricsAggregate {
  interview_prep: TutorInterviewPrepStats;
  language_test: TutorLanguageTestStats;
}

// Progress tracking types
export interface TutorProgressDataPoint {
  session_id: string;
  date: string;
  fluency_score: number | null;
  grammar_score: number | null;
  vocabulary_score: number | null;
  proficiency_level: string | null;
}

export interface TutorProgressResponse {
  sessions: TutorProgressDataPoint[];
  language: string | null;
}

// Session comparison types
export interface TutorSessionComparison {
  current_fluency: number | null;
  current_grammar: number | null;
  current_vocabulary: number | null;
  avg_previous_fluency: number | null;
  avg_previous_grammar: number | null;
  avg_previous_vocabulary: number | null;
  previous_session_count: number;
  fluency_change: number | null;
  grammar_change: number | null;
  vocabulary_change: number | null;
}

// Vocabulary tracking types
export interface VocabularyWord {
  word: string;
  category: string | null;
  used_correctly: boolean | null;
  context: string | null;
  correction: string | null;
  difficulty: string | null;
  times_used: number;
}

export interface VocabularySuggestion {
  word: string;
  meaning: string | null;
  example: string | null;
  difficulty: string | null;
}

export interface TutorVocabularyStats {
  total_unique_words: number;
  mastered_words: VocabularyWord[];
  words_to_review: VocabularyWord[];
  suggested_vocabulary: VocabularySuggestion[];
  language: string;
}

// ===========================================
// ER Copilot (Employee Relations) Types
// ===========================================

export type ERCaseStatus = 'open' | 'in_review' | 'pending_determination' | 'closed';
export type ERDocumentType = 'transcript' | 'policy' | 'email' | 'other';
export type ERProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ERAnalysisType = 'timeline' | 'discrepancies' | 'policy_check' | 'summary' | 'determination';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type SeverityLevel = 'high' | 'medium' | 'low';
export type ViolationSeverity = 'major' | 'minor';

// Case types
export interface ERCase {
  id: string;
  case_number: string;
  title: string;
  description: string | null;
  status: ERCaseStatus;
  created_by: string | null;
  assigned_to: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface ERCaseCreate {
  title: string;
  description?: string;
}

export interface ERCaseUpdate {
  title?: string;
  description?: string;
  status?: ERCaseStatus;
  assigned_to?: string;
}

export interface ERCaseListResponse {
  cases: ERCase[];
  total: number;
}

// Document types
export interface ERDocument {
  id: string;
  case_id: string;
  document_type: ERDocumentType;
  filename: string;
  mime_type: string | null;
  file_size: number | null;
  pii_scrubbed: boolean;
  processing_status: ERProcessingStatus;
  processing_error: string | null;
  parsed_at: string | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface ERDocumentUploadResponse {
  document: ERDocument;
  task_id: string | null;
  message: string;
}

// Timeline Analysis types
export interface TimelineEvent {
  date: string;
  time: string | null;
  description: string;
  participants: string[];
  source_document_id: string;
  source_location: string;
  confidence: ConfidenceLevel;
  evidence_quote: string;
}

export interface TimelineAnalysis {
  events: TimelineEvent[];
  gaps_identified: string[];
  timeline_summary: string;
  generated_at: string;
}

// Discrepancy Analysis types
export interface DiscrepancyStatement {
  source_document_id: string;
  speaker: string;
  quote: string;
  location: string;
}

export interface Discrepancy {
  type: string;
  severity: SeverityLevel;
  description: string;
  statement_1: DiscrepancyStatement;
  statement_2: DiscrepancyStatement;
  analysis: string;
}

export interface CredibilityNote {
  witness: string;
  assessment: string;
  reasoning: string;
}

export interface DiscrepancyAnalysis {
  discrepancies: Discrepancy[];
  credibility_notes: CredibilityNote[];
  summary: string;
  generated_at: string;
}

// Policy Check types
export interface PolicyViolationEvidence {
  source_document_id: string;
  quote: string;
  location: string;
  how_it_violates: string;
}

export interface PolicyViolation {
  policy_section: string;
  policy_text: string;
  severity: ViolationSeverity;
  evidence: PolicyViolationEvidence[];
  analysis: string;
}

export interface PolicyCheckAnalysis {
  violations: PolicyViolation[];
  policies_potentially_applicable: string[];
  summary: string;
  generated_at: string;
}

// Evidence Search types
export interface EvidenceSearchResult {
  chunk_id: string;
  content: string;
  speaker: string | null;
  source_file: string;
  document_type: ERDocumentType;
  page_number: number | null;
  line_range: string | null;
  similarity: number;
  metadata: Record<string, unknown> | null;
}

export interface EvidenceSearchResponse {
  results: EvidenceSearchResult[];
  query: string;
  total_chunks: number;
}

// Task status
export interface ERTaskStatus {
  task_id: string;
  status: string;
  message: string;
}

// Audit log
export interface ERAuditLogEntry {
  id: string;
  case_id: string | null;
  user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface ERAuditLogResponse {
  entries: ERAuditLogEntry[];
  total: number;
}

// ===========================================
// IR (Incident Report) Types
// ===========================================

export type IRIncidentType = 'safety' | 'behavioral' | 'property' | 'near_miss' | 'other';
export type IRSeverity = 'critical' | 'high' | 'medium' | 'low';
export type IRStatus = 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed';
export type IRDocumentType = 'photo' | 'form' | 'statement' | 'other';

export interface IRWitness {
  name: string;
  contact?: string | null;
  statement?: string | null;
}

export interface IRIncident {
  id: string;
  incident_number: string;
  title: string;
  description: string | null;
  incident_type: IRIncidentType;
  severity: IRSeverity;
  status: IRStatus;
  occurred_at: string;
  location: string | null;
  reported_by_name: string;
  reported_by_email: string | null;
  reported_at: string;
  assigned_to: string | null;
  witnesses: IRWitness[];
  category_data: Record<string, unknown>;
  root_cause: string | null;
  corrective_actions: string | null;
  document_count: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface IRIncidentCreate {
  title: string;
  description?: string;
  incident_type: IRIncidentType;
  severity?: IRSeverity;
  occurred_at: string;
  location?: string;
  reported_by_name: string;
  reported_by_email?: string;
  witnesses?: IRWitness[];
  category_data?: Record<string, unknown>;
}

export interface IRIncidentUpdate {
  title?: string;
  description?: string;
  incident_type?: IRIncidentType;
  severity?: IRSeverity;
  status?: IRStatus;
  occurred_at?: string;
  location?: string;
  assigned_to?: string;
  witnesses?: IRWitness[];
  category_data?: Record<string, unknown>;
  root_cause?: string;
  corrective_actions?: string;
}

export interface IRIncidentListResponse {
  incidents: IRIncident[];
  total: number;
}

export interface IRDocument {
  id: string;
  incident_id: string;
  document_type: IRDocumentType;
  filename: string;
  mime_type: string | null;
  file_size: number | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface IRDocumentUploadResponse {
  document: IRDocument;
  message: string;
}

// Analytics types
export interface IRAnalyticsSummary {
  total_incidents: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  recent_count: number;
  avg_resolution_days: number | null;
}

export interface IRTrendDataPoint {
  date: string;
  count: number;
  by_type?: Record<string, number>;
}

export interface IRTrendsAnalysis {
  data: IRTrendDataPoint[];
  period: string;
  start_date: string;
  end_date: string;
}

export interface IRLocationHotspot {
  location: string;
  count: number;
  by_type: Record<string, number>;
  avg_severity_score: number;
}

export interface IRLocationAnalysis {
  hotspots: IRLocationHotspot[];
  total_locations: number;
}

// AI Analysis types
export interface IRCategorizationAnalysis {
  suggested_type: IRIncidentType;
  confidence: number;
  reasoning: string;
  generated_at: string;
}

export interface IRSeverityAnalysis {
  suggested_severity: IRSeverity;
  factors: string[];
  reasoning: string;
  generated_at: string;
}

export interface IRRootCauseAnalysis {
  primary_cause: string;
  contributing_factors: string[];
  prevention_suggestions: string[];
  reasoning: string;
  generated_at: string;
}

export interface IRRecommendationItem {
  action: string;
  priority: 'immediate' | 'short_term' | 'long_term';
  responsible_party?: string;
  estimated_effort?: string;
}

export interface IRRecommendationsAnalysis {
  recommendations: IRRecommendationItem[];
  summary: string;
  generated_at: string;
}

export interface IRSimilarIncident {
  incident_id: string;
  incident_number: string;
  title: string;
  incident_type: IRIncidentType;
  similarity_score: number;
  common_factors: string[];
}

export interface IRSimilarIncidentsAnalysis {
  similar_incidents: IRSimilarIncident[];
  pattern_summary: string | null;
  generated_at: string;
}

// Audit log
export interface IRAuditLogEntry {
  id: string;
  incident_id: string | null;
  user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export type PolicyStatus = 'draft' | 'active' | 'archived';
export type SignatureStatus = 'pending' | 'signed' | 'declined' | 'expired';
export type SignerType = 'candidate' | 'employee' | 'external';

export interface Policy {
  id: string;
  company_id: string;
  company_name: string | null;
  title: string;
  description: string | null;
  content: string;
  file_url: string | null;
  version: string;
  status: PolicyStatus;
  signature_count: number | null;
  pending_signatures: number | null;
  signed_count: number | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface PolicyCreate {
  title: string;
  description: string | null;
  content: string;
  file_url: string | null;
  version?: string;
  status?: PolicyStatus;
}

export interface PolicyUpdate {
  title?: string;
  description?: string | null;
  content?: string;
  file_url?: string | null;
  version?: string;
  status?: PolicyStatus;
}

export interface PolicySignature {
  id: string;
  policy_id: string;
  policy_title: string | null;
  signer_type: SignerType;
  signer_id: string | null;
  signer_name: string;
  signer_email: string;
  status: SignatureStatus;
  signed_at: string | null;
  signature_data: string | null;
  ip_address: string | null;
  token: string;
  expires_at: string;
  created_at: string;
}

export interface SignatureRequest {
  name: string;
  email: string;
  type: SignerType;
  id?: string;
}

export interface SignatureSubmit {
  signature_data: string | null;
  accepted: boolean;
}


export interface IRAuditLogResponse {
  entries: IRAuditLogEntry[];
  total: number;
}
