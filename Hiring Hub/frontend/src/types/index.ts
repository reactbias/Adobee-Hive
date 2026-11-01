export type Department = 
  | 'All Departments'
  | 'Engineering' 
  | 'Product & Design' 
  | 'Sales & Marketing' 
  | 'Data & AI';

export type RequisitionStatus = 
  | 'Active' 
  | 'Urgent' 
  | 'Draft' 
  | 'Closed';

export interface HiringLead {
  name: string;
  role: string;
  avatarUrl: string;
  poolsCount: number;
}

export interface PipelineDistribution {
  review: number;
  aiScreened: number;
  techRound: number;
  offerStage: number;
}

export interface Requisition {
  id: string;
  reqCode: string;
  title: string;
  department: Exclude<Department, 'All Departments'>;
  location: string;
  salaryBand: string;
  equity: string;
  status: RequisitionStatus;
  priorityLabel: string;
  isUrgent?: boolean;
  aiCohortFit: number;
  summary: string;
  skills: string[];
  hiringLead: HiringLead;
  applicantsCount: number;
  unreviewedCount: number;
  pipeline: PipelineDistribution;
  funnelVelocityPercent?: number;
}

export interface CandidateCompetency {
  name: string;
  score: number;
  maxScore: number;
}

export interface CodeRepoTelemetry {
  username: string;
  syncDate: string;
  commitsYear: number;
  reposCount: number;
  commitVelocity: string;
  cohortPercentile: string;
  ossImpact: string;
  ossRole: string;
  architectureSmell: string;
  vulnerabilities: string;
  testCoverage: string;
}

export interface EmploymentRecord {
  title: string;
  company: string;
  period: string;
  duration: string;
  isCurrent: boolean;
  verified: boolean;
  description: string;
  skills: string[];
}

export interface AtsMetadata {
  ingestedAt: string;
  source: string;
  candidateId: string;
  compensationBand: string;
  approvedBudget: string;
  complianceStatus: string;
  checkrTier: string;
  hiringManagerNotes: string;
}

export interface CandidateTelemetry {
  telemetryHash: string;
  overallScore: number;
  percentile: string;
  cosineFit: number;
  competencies: CandidateCompetency[];
  codeRepo: CodeRepoTelemetry;
  employmentHistory: EmploymentRecord[];
  atsMetadata: AtsMetadata;
}

export interface Candidate {
  id: string;
  name: string;
  avatarUrl: string;
  initials?: string;
  title: string;
  currentRole: string;
  currentCompany: string;
  education: string;
  fitScore: number;
  status: 'Ready for Interview' | 'AI Pre-screened' | 'Application Reviewed' | 'New Applicant' | 'Final Round' | 'Offer Extended' | 'Rejected';
  experienceYears: number;
  expectedSalary: string;
  noticePeriod: string;
  location: string;
  email: string;
  phone: string;
  citizenship: string;
  linkedinUrl: string;
  githubUrl: string;
  skills: string[];
  verified: boolean;
  requisitionId: string;
  telemetry?: CandidateTelemetry;
}

export interface ChatMessage {
  id: string;
  sender: 'recruiter' | 'copilot';
  timestamp: string;
  text: string;
  breakdown?: {
    matchedCandidates: string;
    matchedRatio: number;
    removedCandidates: string;
    removedRatio: number;
    highlightProfile: string;
  };
}

export interface ChatSession {
  id: string | number;
  positionId: string;
  positionTitle: string;
  createdAt?: string;
  updatedAt?: string;
  messages: ChatMessage[];
  currentCandidateIds?: number[];
}

export interface FunnelStage {
  stageNumber: string;
  name: string;
  count: number;
  percentage: number;
  colorClass: string;
}

export interface DepartmentQuality {
  department: string;
  icon: string;
  topTierScore: number;
  p50: number;
  p75: number;
  p90: number;
  accentColor: string;
}

export interface SourcingChannel {
  name: string;
  count: number;
  percentage: number;
  colorClass: string;
  dotColor: string;
}

export interface QueryLogItem {
  id: string;
  query: string;
  tag?: string;
  retrievedCount: number;
  accuracyPercent: number;
  matchedCount: number;
  team: string;
  icon: string;
}

export type ActiveView = 
  | 'job-postings' 
  | 'cv-uploader'
  | 'candidate-search' 
  | 'candidate-dossier' 
  | 'chat-sessions'
  | 'analytics-pipelines' 
  | 'settings-team';

// Backend CV Analyzer API Contracts
export interface BackendPosition {
  id: number;
  title: string;
  description: string | null;
  custom_fields?: Array<{ name: string; description?: string }>;
  applicants_count?: number;
  status_counts?: Record<string, number>;
}

export interface BackendUploadResult {
  id?: number;
  filename: string;
  status: string;
  duplicate?: boolean;
  reason?: string;
}

export interface AnalyticsKPIs {
  totalPipeline: number;
  pipelineGrowth: string;
  avgTimeToFillDays: number;
  timeToFillDelta: string;
  screeningAccuracyPercent: number;
  evalsCount: number;
  offerAcceptancePercent: number;
  acceptedCount: string;
}

export interface BackendCandidateBrief {
  id: number;
  document_id: number;
  full_name: string | null;
  email: string | null;
  location: string | null;
  current_job_title: string | null;
  career_level: string | null;
  total_years_experience: number | null;
  key_takeaways: string[];
  phone?: string | null;
  country?: string | null;
  companies?: string[];
  highest_education_level?: string | null;
  technical_skills?: string[];
}

export interface BackendFilterResponse {
  ids: number[];
  count: number;
  action: string;
  explanation: string;
  previous_count: number;
  removed: number;
  plan: {
    action: string;
    conditions: Array<{
      field: string;
      op: string;
      values: string[];
      number?: number | null;
      requirement: string;
    }>;
    ordering?: {
      field: string;
      direction: 'asc' | 'desc';
      limit: number;
    } | null;
    explanation: string;
  } | null;
  trace: Array<{
    field: string;
    op: string;
    values?: string[];
    number?: number | null;
    remaining: number;
  }>;
  candidates: BackendCandidateBrief[];
}

export interface BackendCVDossier {
  document: {
    id: number;
    filename: string;
    status: string;
    error: string | null;
    page_count?: number | null;
    pdf_created_at?: string | null;
    pdf_modified_at?: string | null;
    uploaded_at?: string | null;
    processed_at?: string | null;
  };
  extraction: {
    contact_info?: {
      full_name?: string | null;
      email?: string | null;
      phone?: string | null;
      location?: string | null;
      country?: string | null;
      website?: string | null;
    };
    social_links?: Array<{ platform: string; url: string }>;
    work_experience?: Array<{
      job_title?: string | null;
      job_category?: string | null;
      company?: string | null;
      industry?: string | null;
      location?: string | null;
      country?: string | null;
      employment_type?: string | null;
      start_date?: string | null;
      end_date?: string | null;
      is_current?: boolean;
      duration_months?: number | null;
      team_size_managed?: number | null;
      responsibilities?: string[];
      achievements?: string[];
    }>;
    education?: Array<{
      degree?: string | null;
      degree_level?: string | null;
      field_of_study?: string | null;
      institution?: string | null;
      country?: string | null;
      start_date?: string | null;
      graduation_date?: string | null;
      grade?: string | null;
      honors?: string[];
    }>;
    certifications?: Array<{ name: string; issuer?: string | null; date?: string | null }>;
    languages?: Array<{ language: string; proficiency?: string | null }>;
    technical_skills?: string[];
    soft_skills?: string[];
    software_and_tools?: string[];
    summary?: string | null;
    key_takeaways?: string[];
  } | null;
  derived: {
    total_years_experience?: number | null;
    avg_tenure_months?: number | null;
    num_jobs?: number;
    short_tenures?: Array<{ job_title: string; company: string; duration_months: number }>;
    employment_gaps?: Array<{ from: string; to: string; months: number }>;
    highest_education_level?: string | null;
    career_level?: string | null;
  } | null;
  usage?: {
    model?: string;
    prompt_tokens?: number;
    completion_tokens?: number;
  } | null;
}
