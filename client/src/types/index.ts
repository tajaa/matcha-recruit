// Company types
export interface Company {
  id: string;
  name: string;
  industry: string | null;
  size: string | null;
  ir_guidance_blurb: string | null;
  created_at: string;
  culture_profile: CultureProfile | null;
  interview_count: number;
}

export interface CompanyCreate {
  name: string;
  industry?: string;
  size?: string;
  ir_guidance_blurb?: string;
}

export interface CompanyUpdate {
  name?: string;
  industry?: string;
  size?: string;
  ir_guidance_blurb?: string;
}

// Business Location types
export interface BusinessLocation {
  id: string;
  company_id: string;
  name: string | null;
  address: string | null;
  city: string;
  state: string;
  county: string | null;
  zipcode: string;
  is_active: boolean;
  last_compliance_check: string | null;
  created_at: string;
  updated_at: string;
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
export type UserRole = 'admin' | 'client' | 'candidate' | 'employee' | 'broker';

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

export interface BusinessRegister {
  company_name: string;
  industry?: string;
  company_size?: string;
  headcount: number;
  email: string;
  password: string;
  name: string;
  phone?: string;
  job_title?: string;
  invite_token?: string;
}

export interface TestAccountRegister {
  company_name?: string;
  industry?: string;
  company_size?: string;
  email: string;
  password?: string;
  name: string;
  phone?: string;
  job_title?: string;
}

export interface TestAccountProvisionResponse {
  status: string;
  message: string;
  company_id: string;
  company_name: string;
  user_id: string;
  email: string;
  password: string;
  generated_password: boolean;
}

export interface BusinessInvite {
  id: string;
  token: string;
  invite_url: string;
  status: string;
  note: string | null;
  created_by_email: string;
  used_by_company_name: string | null;
  expires_at: string;
  used_at: string | null;
  created_at: string;
}

export interface AdminProfile {
  id: string;
  user_id: string;
  name: string;
  email: string;
  created_at: string;
}

export type EnabledFeatures = Record<string, boolean>;

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
  enabled_features?: EnabledFeatures;
}

export interface CompanyWithFeatures {
  id: string;
  company_name: string;
  industry: string | null;
  size: string | null;
  status: string;
  enabled_features: EnabledFeatures;
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

export interface BrokerAuthProfile {
  id: string;
  user_id: string;
  name?: string;
  broker_id: string;
  broker_name: string;
  broker_slug: string;
  branding_mode: 'direct' | 'co_branded' | 'white_label';
  brand_display_name: string;
  member_role: string;
  broker_status: string;
  billing_mode: string;
  invoice_owner: string;
  support_routing: string;
  terms_required_version: string;
  terms_accepted: boolean;
  terms_accepted_at: string | null;
  created_at: string;
}

export interface BrokerBrandingRuntime {
  broker_id: string;
  broker_slug: string;
  broker_name: string;
  branding_mode: 'direct' | 'co_branded' | 'white_label';
  brand_display_name: string;
  brand_legal_name: string | null;
  logo_url: string | null;
  favicon_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  login_subdomain: string | null;
  custom_login_url: string | null;
  support_email: string | null;
  support_phone: string | null;
  support_url: string | null;
  email_from_name: string | null;
  email_from_address: string | null;
  powered_by_badge: boolean;
  hide_matcha_identity: boolean;
  mobile_branding_enabled: boolean;
  theme: Record<string, unknown>;
  resolved_by: 'slug' | 'subdomain';
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
  profile: AdminProfile | ClientProfile | CandidateAuthProfile | BrokerAuthProfile | null;
  onboarding_needed?: Record<string, boolean>;
}

export interface BrokerClientSetup {
  id: string;
  broker_id: string;
  company_id: string;
  company_name: string;
  company_status: string;
  industry: string | null;
  company_size: string | null;
  status: 'draft' | 'invited' | 'activated' | 'expired' | 'cancelled';
  link_status: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  headcount_hint: number | null;
  preconfigured_features: Record<string, boolean>;
  onboarding_template: Record<string, unknown>;
  link_permissions: Record<string, unknown>;
  invite_token: string | null;
  invite_url: string | null;
  invite_expires_at: string | null;
  invited_at: string | null;
  activated_at: string | null;
  expired_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  google_workspace: {
    connected: boolean;
    status: 'disconnected' | 'connected' | 'error' | 'needs_action' | string;
    auto_provision_on_employee_create: boolean;
  } | null;
}

export interface BrokerClientSetupListResponse {
  setups: BrokerClientSetup[];
  total: number;
  expired_count: number;
}

export interface BrokerClientSetupCreateRequest {
  company_name: string;
  industry?: string;
  company_size?: string;
  headcount?: number;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  preconfigured_features?: Record<string, boolean>;
  onboarding_template?: Record<string, unknown>;
  link_permissions?: Record<string, unknown>;
  invite_immediately?: boolean;
  invite_expires_days?: number;
}

export interface BrokerClientSetupUpdateRequest {
  company_name?: string;
  industry?: string;
  company_size?: string;
  headcount?: number;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  preconfigured_features?: Record<string, boolean>;
  onboarding_template?: Record<string, unknown>;
}

export interface BrokerPortfolioCompanyMetric {
  company_id: string;
  company_name: string;
  link_status: string;
  setup_status: string;
  policy_compliance_rate: number;
  open_action_items: number;
  active_employee_count: number;
  risk_signal: 'healthy' | 'watch' | 'at_risk';
}

export interface BrokerPortfolioReportResponse {
  summary: {
    total_linked_companies: number;
    active_link_count: number;
    pending_setup_count: number;
    expired_setup_count: number;
    healthy_companies: number;
    at_risk_companies: number;
    average_policy_compliance_rate: number;
    open_action_item_total: number;
  };
  setup_status_counts: Record<string, number>;
  companies: BrokerPortfolioCompanyMetric[];
  redaction: {
    employee_level_pii_included: boolean;
    incident_detail_included: boolean;
    note: string;
  };
}

export interface GoogleWorkspaceConnectionRequest {
  mode: 'mock' | 'api_token';
  domain?: string;
  admin_email?: string;
  default_org_unit?: string;
  default_groups?: string[];
  auto_provision_on_employee_create?: boolean;
  access_token?: string;
  test_connection?: boolean;
}

export interface GoogleWorkspaceConnectionStatus {
  provider: 'google_workspace';
  connected: boolean;
  status: 'disconnected' | 'connected' | 'error' | 'needs_action' | string;
  mode: 'mock' | 'api_token' | null;
  domain: string | null;
  admin_email: string | null;
  default_org_unit: string | null;
  default_groups: string[];
  auto_provision_on_employee_create: boolean;
  has_access_token: boolean;
  last_tested_at: string | null;
  last_error: string | null;
  updated_at: string | null;
}

export interface ProvisioningStepStatus {
  step_id: string;
  step_key: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'needs_action' | 'rolled_back' | 'cancelled' | string;
  attempts: number;
  last_error: string | null;
  last_response: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProvisioningRunStatus {
  run_id: string;
  company_id: string;
  employee_id: string;
  provider: 'google_workspace' | 'slack' | string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'needs_action' | 'rolled_back' | 'cancelled' | string;
  trigger_source: 'manual' | 'employee_create' | 'scheduled' | 'retry' | 'api' | string;
  triggered_by: string | null;
  retry_of_run_id: string | null;
  last_error: string | null;
  started_at: string | null;
  completed_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  steps: ProvisioningStepStatus[];
}

export interface ExternalIdentity {
  provider: 'google_workspace' | 'slack' | string;
  external_user_id: string | null;
  external_email: string | null;
  status: 'active' | 'suspended' | 'deprovisioned' | 'error' | string;
  raw_profile: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EmployeeGoogleWorkspaceProvisioningStatus {
  connection: GoogleWorkspaceConnectionStatus;
  external_identity: ExternalIdentity | null;
  runs: ProvisioningRunStatus[];
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
export type ERCaseNoteType = 'general' | 'question' | 'answer' | 'guidance' | 'system';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type SeverityLevel = 'high' | 'medium' | 'low';
export type ViolationSeverity = 'major' | 'minor';
export type ERIntakeObjective = 'timeline' | 'discrepancies' | 'policy' | 'general';
export type ERIntakeImmediateRisk = 'yes' | 'no' | 'unsure';

export interface ERCaseIntakeContext {
  assistance_requested?: boolean;
  no_documents_at_intake?: boolean;
  captured_at?: string;
  assistance?: {
    mode?: 'auto' | 'manual';
    last_reviewed_signature?: string;
    last_reviewed_doc_ids?: string[];
    last_reviewed_at?: string;
    last_run_status?: 'completed' | 'partial' | 'failed';
  };
  answers?: {
    immediate_risk?: ERIntakeImmediateRisk;
    objective?: ERIntakeObjective;
    complaint_format?: 'verbal' | 'written' | 'both' | 'unknown';
    witnesses?: string;
    additional_notes?: string;
  };
}

// Case types
export interface ERCase {
  id: string;
  case_number: string;
  title: string;
  description: string | null;
  intake_context: ERCaseIntakeContext | null;
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
  intake_context?: ERCaseIntakeContext | null;
}

export interface ERCaseUpdate {
  title?: string;
  description?: string;
  status?: ERCaseStatus;
  assigned_to?: string;
  intake_context?: ERCaseIntakeContext | null;
}

export interface ERCaseListResponse {
  cases: ERCase[];
  total: number;
}

export interface ERCaseNote {
  id: string;
  case_id: string;
  note_type: ERCaseNoteType;
  content: string;
  metadata: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string;
}

export interface ERCaseNoteCreate {
  note_type?: ERCaseNoteType;
  content: string;
  metadata?: Record<string, unknown>;
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
  company_id: string | null;
  location_id: string | null;
  company_name: string | null;
  location_name: string | null;
  location_city: string | null;
  location_state: string | null;
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
  company_id?: string;
  location_id?: string;
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
  company_id?: string;
  location_id?: string;
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
  from_cache?: boolean;
  cache_reason?: string;
}

export interface IRSeverityAnalysis {
  suggested_severity: IRSeverity;
  factors: string[];
  reasoning: string;
  generated_at: string;
  from_cache?: boolean;
  cache_reason?: string;
}

export interface IRRootCauseAnalysis {
  primary_cause: string;
  contributing_factors: string[];
  prevention_suggestions: string[];
  reasoning: string;
  generated_at: string;
  from_cache?: boolean;
  cache_reason?: string;
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
  from_cache?: boolean;
  cache_reason?: string;
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
  from_cache?: boolean;
  cache_reason?: string;
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
  file_url?: string | null;
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

export type HandbookStatus = 'draft' | 'active' | 'archived';
export type HandbookMode = 'single_state' | 'multi_state';
export type HandbookSourceType = 'template' | 'upload';
export type HandbookSectionType = 'core' | 'state' | 'custom' | 'uploaded';
export type HandbookChangeStatus = 'pending' | 'accepted' | 'rejected';

export interface CompanyHandbookProfile {
  company_id?: string;
  legal_name: string;
  dba: string | null;
  ceo_or_president: string;
  headcount: number | null;
  remote_workers: boolean;
  minors: boolean;
  tipped_employees: boolean;
  union_employees: boolean;
  federal_contracts: boolean;
  group_health_insurance: boolean;
  background_checks: boolean;
  hourly_employees: boolean;
  salaried_employees: boolean;
  commissioned_employees: boolean;
  tip_pooling: boolean;
  updated_by?: string | null;
  updated_at?: string;
}

export interface HandbookScope {
  id?: string;
  state: string;
  city: string | null;
  zipcode: string | null;
  location_id: string | null;
}

export interface HandbookSection {
  id?: string;
  section_key: string;
  title: string;
  content: string;
  section_order: number;
  section_type: HandbookSectionType;
  jurisdiction_scope?: Record<string, unknown>;
}

export interface HandbookListItem {
  id: string;
  title: string;
  status: HandbookStatus;
  mode: HandbookMode;
  source_type: HandbookSourceType;
  active_version: number;
  scope_states: string[];
  pending_changes_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface HandbookDetail {
  id: string;
  company_id: string;
  title: string;
  status: HandbookStatus;
  mode: HandbookMode;
  source_type: HandbookSourceType;
  active_version: number;
  file_url: string | null;
  file_name: string | null;
  scopes: HandbookScope[];
  profile: CompanyHandbookProfile;
  sections: HandbookSection[];
  created_at: string;
  updated_at: string;
  published_at: string | null;
  created_by: string | null;
}

export interface HandbookCreate {
  title: string;
  mode: HandbookMode;
  source_type: HandbookSourceType;
  scopes: Omit<HandbookScope, 'id'>[];
  profile: CompanyHandbookProfile;
  custom_sections?: HandbookSection[];
  file_url?: string | null;
  file_name?: string | null;
  create_from_template?: boolean;
}

export interface HandbookUpdate {
  title?: string;
  mode?: HandbookMode;
  scopes?: Omit<HandbookScope, 'id'>[];
  profile?: CompanyHandbookProfile;
  sections?: HandbookSection[];
  file_url?: string | null;
  file_name?: string | null;
}

export interface HandbookChangeRequest {
  id: string;
  handbook_id: string;
  handbook_version_id: string;
  alert_id: string | null;
  section_key: string | null;
  old_content: string | null;
  proposed_content: string;
  rationale: string | null;
  source_url: string | null;
  effective_date: string | null;
  status: HandbookChangeStatus;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface HandbookDistributionResult {
  handbook_id: string;
  handbook_version: number;
  assigned_count: number;
  skipped_existing_count: number;
  distributed_at: string;
}

export interface HandbookAcknowledgementSummary {
  handbook_id: string;
  handbook_version: number;
  assigned_count: number;
  signed_count: number;
  pending_count: number;
  expired_count: number;
}


export interface IRAuditLogResponse {
  entries: IRAuditLogEntry[];
  total: number;
}

// Blog types
export type BlogStatus = 'draft' | 'published' | 'archived';

export interface BlogPost {
  id: string;
  title: string;
  slug: string;
  content: string;
  excerpt: string | null;
  cover_image: string | null;
  status: BlogStatus;
  tags: string[];
  meta_title: string | null;
  meta_description: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  author_id?: string | null;
  author_name?: string | null;
  author_email?: string | null;
  likes_count: number;
  liked_by_me: boolean;
}

export interface BlogPostCreate {
  title: string;
  slug: string;
  content: string;
  excerpt?: string | null;
  cover_image?: string | null;
  status?: BlogStatus;
  tags?: string[];
  meta_title?: string | null;
  meta_description?: string | null;
}

export interface BlogPostUpdate {
  title?: string;
  slug?: string;
  content?: string;
  excerpt?: string | null;
  cover_image?: string | null;
  status?: BlogStatus;
  tags?: string[];
  meta_title?: string | null;
  meta_description?: string | null;
}

export interface BlogListResponse {
  items: BlogPost[];
  total: number;
}

export type CommentStatus = 'pending' | 'approved' | 'rejected' | 'spam';

export interface BlogComment {
  id: string;
  post_id: string;
  user_id: string | null;
  author_name: string;
  content: string;
  status: CommentStatus;
  created_at: string;
  post_title?: string;
}

export interface BlogCommentCreate {
  content: string;
  author_name?: string;
}

// Offer Letter types
export type OfferLetterStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';

export type OfferLetterEmploymentType = 'Full-Time Exempt' | 'Full-Time Hourly' | 'Part-Time Hourly' | 'Contract' | 'Internship';

export interface OfferLetter {
  id: string;
  candidate_name: string;
  position_title: string;
  company_name: string;
  status: OfferLetterStatus;
  salary: string | null;
  bonus: string | null;
  stock_options: string | null;
  start_date: string | null;
  employment_type: string | null;
  location: string | null;
  benefits: string | null;
  manager_name: string | null;
  manager_title: string | null;
  expiration_date: string | null;
  created_at: string;
  updated_at: string;
  sent_at: string | null;
  // Structured benefits
  benefits_medical: boolean;
  benefits_medical_coverage: number | null;
  benefits_medical_waiting_days: number;
  benefits_dental: boolean;
  benefits_vision: boolean;
  benefits_401k: boolean;
  benefits_401k_match: string | null;
  benefits_wellness: string | null;
  benefits_pto_vacation: boolean;
  benefits_pto_sick: boolean;
  benefits_holidays: boolean;
  benefits_other: string | null;
  // Contingencies
  contingency_background_check: boolean;
  contingency_credit_check: boolean;
  contingency_drug_screening: boolean;
  // Company logo
  company_logo_url: string | null;
}

export interface OfferLetterCreate {
  candidate_name: string;
  position_title: string;
  company_name: string;
  salary?: string;
  bonus?: string;
  stock_options?: string;
  start_date?: string;
  employment_type?: string;
  location?: string;
  benefits?: string;
  manager_name?: string;
  manager_title?: string;
  expiration_date?: string;
  // Structured benefits
  benefits_medical?: boolean;
  benefits_medical_coverage?: number;
  benefits_medical_waiting_days?: number;
  benefits_dental?: boolean;
  benefits_vision?: boolean;
  benefits_401k?: boolean;
  benefits_401k_match?: string;
  benefits_wellness?: string;
  benefits_pto_vacation?: boolean;
  benefits_pto_sick?: boolean;
  benefits_holidays?: boolean;
  benefits_other?: string;
  // Contingencies
  contingency_background_check?: boolean;
  contingency_credit_check?: boolean;
  contingency_drug_screening?: boolean;
  // Company logo
  company_logo_url?: string;
}

export interface OfferLetterUpdate {
  candidate_name?: string;
  position_title?: string;
  company_name?: string;
  status?: OfferLetterStatus;
  salary?: string;
  bonus?: string;
  stock_options?: string;
  start_date?: string;
  employment_type?: string;
  location?: string;
  benefits?: string;
  manager_name?: string;
  manager_title?: string;
  expiration_date?: string;
  // Structured benefits
  benefits_medical?: boolean;
  benefits_medical_coverage?: number;
  benefits_medical_waiting_days?: number;
  benefits_dental?: boolean;
  benefits_vision?: boolean;
  benefits_401k?: boolean;
  benefits_401k_match?: string;
  benefits_wellness?: string;
  benefits_pto_vacation?: boolean;
  benefits_pto_sick?: boolean;
  benefits_holidays?: boolean;
  benefits_other?: string;
  // Contingencies
  contingency_background_check?: boolean;
  contingency_credit_check?: boolean;
  contingency_drug_screening?: boolean;
  // Company logo
  company_logo_url?: string;
}

// Business Registration types
export type BusinessRegistrationStatus = 'pending' | 'approved' | 'rejected';

export interface BusinessRegistration {
  id: string;
  company_name: string;
  industry: string | null;
  company_size: string | null;
  owner_email: string;
  owner_name: string;
  owner_phone: string | null;
  owner_job_title: string | null;
  status: BusinessRegistrationStatus;
  rejection_reason: string | null;
  approved_at: string | null;
  approved_by_email: string | null;
  created_at: string;
}

export interface BusinessRegistrationListResponse {
  registrations: BusinessRegistration[];
  total: number;
}

// Poster types
export type PosterTemplateStatus = 'pending' | 'generated' | 'failed';
export type PosterOrderStatus = 'requested' | 'quoted' | 'processing' | 'shipped' | 'delivered' | 'cancelled';

export interface PosterTemplate {
  id: string;
  jurisdiction_id: string;
  title: string;
  description: string | null;
  version: number;
  pdf_url: string | null;
  pdf_generated_at: string | null;
  categories_included: string[] | null;
  requirement_count: number;
  status: PosterTemplateStatus;
  jurisdiction_name: string | null;
  state: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PosterTemplateListResponse {
  templates: PosterTemplate[];
  total: number;
}

export interface PosterOrderItem {
  id: string;
  template_id: string;
  quantity: number;
  template_title: string | null;
  jurisdiction_name: string | null;
}

export interface PosterOrder {
  id: string;
  company_id: string;
  location_id: string;
  status: PosterOrderStatus;
  requested_by: string | null;
  admin_notes: string | null;
  quote_amount: number | null;
  shipping_address: string | null;
  tracking_number: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  company_name: string | null;
  location_name: string | null;
  location_city: string | null;
  location_state: string | null;
  requested_by_email: string | null;
  items: PosterOrderItem[];
}

export interface PosterOrderListResponse {
  orders: PosterOrder[];
  total: number;
}

export interface AvailablePoster {
  location_id: string;
  location_name: string | null;
  location_city: string;
  location_state: string;
  jurisdiction_id: string | null;
  template_id: string | null;
  template_title: string | null;
  template_status: PosterTemplateStatus | null;
  template_version: number | null;
  pdf_url: string | null;
  pdf_generated_at: string | null;
  categories_included: string[] | null;
  has_active_order: boolean;
}

export interface PosterOrderCreate {
  location_id: string;
  template_ids: string[];
  quantity?: number;
  shipping_address?: string;
}

export interface PosterOrderUpdate {
  status?: PosterOrderStatus;
  admin_notes?: string;
  quote_amount?: number;
  tracking_number?: string;
}
