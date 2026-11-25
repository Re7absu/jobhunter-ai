export const STATUSES = [
  "Discovered",
  "Analyzed",
  "Awaiting Approval",
  "Approved",
  "Ready to Apply",
  "Applied",
  "Follow-up Required",
  "Response Received",
  "Interview Scheduled",
  "Rejected",
  "Closed",
] as const;
export type ApplicationStatus = (typeof STATUSES)[number];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Skill {
  id: number;
  name: string;
  category: string;
  source: string;
  evidence: string | null;
}

export interface Profile {
  id: number;
  full_name: string | null;
  headline: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  summary: string | null;
  education: Record<string, string | null>[];
  experience: { company?: string; title?: string; start?: string; end?: string; description?: string; highlights?: string[] }[];
  projects: { name?: string; description?: string; technologies?: string[] }[];
  certifications: { name?: string; issuer?: string; date?: string }[];
  languages: string[];
  target_roles: string[];
  years_experience: number | null;
  extraction_warnings: string[];
  active_cv_id: number | null;
  skills: Skill[];
  updated_at: string;
}

export interface CV {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  is_active: boolean;
  parse_status: string;
  parse_method: string | null;
  parse_error: string | null;
  parsed_at: string | null;
  created_at: string;
}

export interface Company {
  id: number;
  name: string;
  domain: string | null;
  website: string | null;
  linkedin_url: string | null;
  city: string | null;
  industry: string | null;
  description: string | null;
  careers_url: string | null;
  logo_url: string | null;
  recruitment_email: string | null;
  email_verified: boolean;
  email_source_url: string | null;
  ats_type: string | null;
  ats_slug: string | null;
  tracked: boolean;
  tracking_source: string | null;
  board_detected_from: string | null;
  last_scanned_at: string | null;
  scan_error: string | null;
  source: string | null;
  discovered_at: string;
  last_enriched_at: string | null;
  enrichment_error: string | null;
  job_count: number;
}

export interface Match {
  id: number;
  job_id: number;
  score: number;
  category: string;
  matching_skills: string[];
  missing_skills: string[];
  transferable_skills: string[];
  explanation: string | null;
  recommendation: string;
  should_apply: boolean;
  method: string;
  model: string | null;
  created_at: string;
}

export interface Job {
  id: number;
  company_id: number;
  company_name: string | null;
  title: string;
  category: string;
  role_family: string | null;
  city: string | null;
  location_raw: string | null;
  employment_type: string | null;
  experience_level: string | null;
  experience_min_years: number | null;
  salary_text: string | null;
  posted_at: string | null;
  application_url: string | null;
  source: string;
  publisher: string | null;
  source_url: string;
  discovery_method: string;
  seen_sources: { source: string; publisher: string | null; url: string; at: string }[];
  is_active: boolean;
  discovered_at: string;
  last_verified_at: string | null;
  updated_at: string | null;
  match_score: number | null;
  match_category: string | null;
  application_id: number | null;
  application_status: string | null;
}

export interface JobDetail extends Job {
  description: string | null;
  experience_text: string | null;
  requirements: { requirement_type: string; name: string; is_required: boolean }[];
  match: Match | null;
  company: Company | null;
}

export interface Email {
  id: number;
  version: number;
  subject: string;
  body: string;
  status: string;
  generation_method: string;
  model: string | null;
  warnings: string[];
  edited: boolean;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailHistory {
  id: number;
  application_id: number | null;
  direction: string;
  from_email: string | null;
  to_email: string | null;
  subject: string | null;
  body: string | null;
  attachment_name: string | null;
  gmail_message_id: string | null;
  gmail_thread_id: string | null;
  status: string;
  error: string | null;
  created_at: string;
  company_name: string | null;
  job_title: string | null;
}

export interface FollowUp {
  id: number;
  application_id: number;
  due_at: string;
  status: string;
  subject: string | null;
  body: string | null;
  sent_at: string | null;
  company_name: string | null;
  job_title: string | null;
  method: string | null;
}

export interface ApplicationRow {
  id: number;
  job_id: number;
  company_id: number;
  company_name: string;
  job_title: string;
  city: string | null;
  category: string;
  match_score: number | null;
  match_category: string | null;
  method: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  status_changed_at: string;
  source_url: string;
  application_url: string | null;
  recipient_email: string | null;
  experience_level: string | null;
  created_at: string;
}

export interface ApplicationDetail extends ApplicationRow {
  notes: string | null;
  interview_at: string | null;
  response_at: string | null;
  gmail_thread_id: string | null;
  job: JobDetail;
  emails: Email[];
  history: { from_status: string | null; to_status: string; changed_by: string; note: string | null; created_at: string }[];
  email_history: EmailHistory[];
  follow_ups: FollowUp[];
}

export interface Kpis {
  total_companies: number;
  total_jobs: number;
  active_jobs: number;
  qualified_opportunities: number;
  applications_today: number;
  applications_this_week: number;
  pending_applications: number;
  awaiting_approval: number;
  responses_received: number;
  interviews_scheduled: number;
  total_applied: number;
}

export interface Charts {
  applications_per_day: { date: string; count: number }[];
  applications_per_week: { week: string; count: number }[];
  applications_by_city: { city: string; count: number }[];
  applications_by_category: { category: string; count: number }[];
  companies_contacted: number;
  response_rate: number;
  interview_rate: number;
  average_match_score: number | null;
  match_score_distribution: { bucket: string; count: number }[];
  status_breakdown: { status: string; count: number }[];
}

export interface ContactedCompany {
  application_id: number;
  company: string;
  job_title: string;
  city: string | null;
  method: string | null;
  recipient: string | null;
  applied_at: string;
  source_url: string;
}

export interface DailyReport {
  id: number;
  report_date: string;
  new_companies: number;
  new_jobs: number;
  jobs_analyzed: number;
  qualified: number;
  emails_generated: number;
  applications_sent: number;
  responses: number;
  companies_contacted: ContactedCompany[];
  summary: Record<string, unknown>;
  updated_at: string;
}

export interface AutomationSettings {
  paused: boolean;
  auto_discovery: boolean;
  search_frequency_hours: number;
  run_hour: number;
  preferred_cities: string[];
  job_categories: string[];
  custom_job_titles: string[];
  experience_levels: string[];
  include_arabic_titles: boolean;
  sources_enabled: string[];
  max_queries_per_run: number;
  max_boards_per_run: number;
  max_jobs_to_analyze_per_run: number;
  min_match_score: number;
  max_daily_applications: number;
  auto_generate_emails: boolean;
  follow_up_after_days: number;
  job_max_age_days: number;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface Run {
  id: number;
  trigger: string;
  status: string;
  current_step: string | null;
  stats: Record<string, unknown>;
  log: { at: string; step: string; msg: string | null }[];
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface AutomationStatus {
  running: boolean;
  paused: boolean;
  next_run_at: string | null;
  openai_error: string | null;
  integrations: Record<string, boolean>;
}

export interface FormAssist {
  application_url: string;
  page_status: string;
  fields: { name: string; label: string; type: string; required: boolean; profile_key: string | null; suggested_value: string | null }[];
  profile_values: Record<string, string | null>;
  notes: string[];
}
