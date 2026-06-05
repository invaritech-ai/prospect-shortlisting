export type UploadRead = {
  id: string
  campaign_id: string
  filename: string
  row_count: number
  created_at: string
}

export type UploadCreateResult = {
  upload: UploadRead
  new_count: number
  dupe_count: number
}

export type UploadList = {
  total: number
  limit: number
  offset: number
  items: UploadRead[]
}

export type DomainRead = {
  id: string
  campaign_id: string
  upload_id: string | null
  raw_url: string
  normalized_url: string
  domain: string
  scrape_status: string | null
  decision_status: string | null
  fetch_status: string | null
  verify_status: string | null
  created_at: string
  latest_scrape_updated_at: string | null
  latest_scrape_result_id: string | null
  latest_scrape_error_code: string | null
  latest_scrape_failure_class: string | null
  latest_scrape_retryable: boolean | null
  latest_scrape_final_url: string | null
}

export type DomainList = {
  total: number
  limit: number
  offset: number
  items: DomainRead[]
}

export type FullPipelineCompanyRow = {
  domain_id: string
  campaign_id: string
  raw_url: string
  normalized_url: string
  domain: string
  scrape_status: string | null
  decision_status: string | null
  fetch_status: string | null
  verify_status: string | null
  created_at: string
  latest_scrape_updated_at: string | null
  latest_scrape_error_code: string | null
  latest_scrape_failure_class: string | null
  latest_scrape_retryable: boolean | null
  latest_scrape_final_url: string | null
  classification_state: string | null
  effective_label: string | null
  contacts_found: number
  emails_found: number
  email_contact_count: number
  valid_email_count: number
  latest_contact_updated_at: string | null
  last_activity: string
}

export type FullPipelineCompanyList = {
  total: number
  limit: number
  offset: number
  items: FullPipelineCompanyRow[]
}

export type AiReviewDomainRow = {
  domain_id: string
  campaign_id: string
  domain: string
  raw_url: string
  normalized_url: string
  classification_result_id: string | null
  classification_state: string | null
  predicted_label: string | null
  confidence: number | null
  reasoning_json: Record<string, unknown> | null
  evidence_json: Record<string, unknown> | null
  manual_label: string | null
  manual_thumbs: string | null
  manual_comment: string | null
  manually_reviewed_at: string | null
  effective_label: string | null
  effective_confidence: number | null
  pages_reviewed: number
  activity_at: string
}

export type AiReviewDomainList = {
  total: number
  limit: number
  offset: number
  items: AiReviewDomainRow[]
}

export type AiReviewDomainAnalysis = AiReviewDomainRow

export type AiReviewLabelCounts = {
  all: number
  unclassified: number
  possible: number
  unknown: number
  crap: number
}

export type AiReviewJobCreate = {
  campaign_id: string
  domain_ids?: string[]
  label?: string | null
  letter?: string | null
  search?: string | null
}

export type AiReviewJobRead = {
  id: string
  campaign_id: string
  state: string
  selected_domain_count: number
  queued_count: number
  success_count: number
  failed_count: number
  created_at: string
  finished_at: string | null
}

export type AiReviewJobStatusRead = {
  batch_id: string
  campaign_id: string
  state: string
  selected: number
  queued: number
  running: number
  succeeded: number
  failed: number
  terminal: number
  queue_todo: number
  queue_doing: number
  queue_succeeded: number
  queue_failed: number
  queue_cancelled: number
  queue_aborting: number
  queue_aborted: number
  created_at: string
  finished_at: string | null
}

export type EmailFetchCompanyStatus = 'pending' | 'running' | 'done' | 'failed' | 'no_match'
export type EmailFetchMode = 'fetch' | 'refetch'

export type EmailFetchCriteriaRead = {
  id: string | null
  campaign_id: string
  include_titles: string[]
  exclude_titles: string[]
  target_contacts_per_company: number
  criteria_hash: string
  is_active: boolean
  created_at: string | null
}

export type EmailFetchCriteriaSaveRequest = {
  campaign_id: string
  include_titles: string[]
  exclude_titles: string[]
  target_contacts_per_company: 3
}

export type EmailFetchPreviewRequest = {
  campaign_id: string
  domain_ids: string[]
  mode?: EmailFetchMode
}

export type EmailFetchBatchCreate = EmailFetchPreviewRequest

export type EmailFetchCreditPlan = {
  apollo_preview_is_free: boolean
  title_hint_count: number
  snov_positions_per_search: number
  snov_title_chunks_per_company: number
  estimated_apollo_reveals: number
  estimated_snov_discovery_searches: number
  estimated_snov_email_lookups: number
}

export type EmailFetchPreviewCandidate = {
  domain_id: string
  domain: string
  provider: string
  provider_person_id: string
  first_name: string
  last_name: string
  title: string
  linkedin_url: string | null
}

export type EmailFetchPreviewDomain = {
  domain_id: string
  domain: string
  matched_candidate_count: number
  estimated_apollo_reveals: number
  estimated_snov_fallback: number
  candidates: EmailFetchPreviewCandidate[]
  warnings: string[]
}

export type EmailFetchPreviewRead = {
  campaign_id: string
  mode: EmailFetchMode
  selected_domain_count: number
  target_contacts_per_company: number
  estimated_apollo_reveals: number
  estimated_snov_fallback_min: number
  credit_plan: EmailFetchCreditPlan
  criteria_hash: string
  criteria_snapshot: Record<string, unknown>
  domains: EmailFetchPreviewDomain[]
  warnings: string[]
}

export type EmailFetchBatchRead = {
  id: string
  campaign_id: string
  state: string
  selected_domain_count: number
  queued_count: number
  success_count: number
  failed_count: number
  criteria_hash: string | null
  criteria_snapshot: Record<string, unknown> | null
  provider_order: string[]
  result_summary: Record<string, unknown> | null
  created_at: string
  finished_at: string | null
}

export type EmailFetchCompanyCounts = {
  all: number
  pending: number
  running: number
  done: number
  failed: number
  no_match: number
  contacts_found: number
  emails_found: number
  fetched_people_found: number
}

export type EmailFetchCompanyRow = {
  domain_id: string
  campaign_id: string
  domain: string
  normalized_url: string
  fetch_status: string | null
  status: EmailFetchCompanyStatus
  contacts_found: number
  emails_found: number
  fetched_people_found: number
  updated_at: string
}

export type EmailFetchCompanyList = {
  total: number
  limit: number
  offset: number
  counts: EmailFetchCompanyCounts
  items: EmailFetchCompanyRow[]
}

export type EmailFetchCompanyIds = {
  ids: string[]
  total: number
  limit: number
  offset: number
}

export type EmailVerificationStatus = 'pending' | 'checking' | 'stale' | 'valid' | 'undeliverable' | 'catch_all' | 'unknown' | 'failed'

export type EmailVerificationCounts = {
  all: number
  pending: number
  checking: number
  stale: number
  valid: number
  undeliverable: number
  catch_all: number
  unknown: number
  failed: number
}

export type EmailVerificationContactRow = {
  contact_id: string
  campaign_id: string
  domain_id: string
  domain: string
  first_name: string
  last_name: string
  title: string | null
  linkedin_url: string | null
  selected_email: string
  status: EmailVerificationStatus
  verified_at: string | null
  updated_at: string
  action_label: string | null
}

export type EmailVerificationContactList = {
  total: number
  limit: number
  offset: number
  counts: EmailVerificationCounts
  items: EmailVerificationContactRow[]
}

export type EmailVerificationContactIds = {
  ids: string[]
  total: number
  limit: number
  offset: number
}

export type EmailVerificationPreviewRequest = {
  campaign_id: string
  contact_ids: string[]
}

export type EmailVerificationPreviewRead = {
  campaign_id: string
  selected_count: number
  eligible_count: number
  cached_count: number
  paid_validation_count: number
  skipped_count: number
  skipped_reasons: Record<string, number>
  max_batch_size: number
  warnings: string[]
}

export type EmailVerificationBatchCreate = {
  campaign_id: string
  contact_ids: string[]
}

export type EmailVerificationBatchRead = {
  id: string
  campaign_id: string
  state: string
  selected_count: number
  queued_count: number
  verified_count: number
  valid_count: number
  invalid_count: number
  skipped_count: number
  result_summary: Record<string, unknown> | null
  created_at: string
  finished_at: string | null
}

export type ContactRead = {
  id: string
  campaign_id: string
  domain_id: string
  domain: string
  first_name: string
  last_name: string
  title: string | null
  linkedin_url: string | null
  title_match: boolean
  selected_email: string | null
  selected_email_provider: string | null
  verification_status: string | null
  criteria_hash: string | null
  provider_evidence_json: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type ContactList = {
  total: number
  limit: number
  offset: number
  items: ContactRead[]
}

export type FetchedPersonRead = {
  id: string
  campaign_id: string
  domain_id: string
  domain: string
  email_fetch_batch_id: string | null
  contact_id: string | null
  criteria_hash: string | null
  provider: string
  provider_person_id: string
  first_name: string
  last_name: string
  title: string | null
  linkedin_url: string | null
  match_status: string
  match_reason: string
  email_lookup_attempted: boolean
  email_result: string | null
  email_status: string | null
  email_error_code: string
  created_at: string
  updated_at: string
}

export type FetchedPersonList = {
  total: number
  limit: number
  offset: number
  items: FetchedPersonRead[]
}

export type CampaignRead = {
  id: string
  name: string
  description: string | null
  upload_count: number
  company_count: number
  scrape_count: number
  classified_count: number
  possible_count: number
  contact_count: number
  valid_email_count: number
  created_at: string
  updated_at: string
}

export type CampaignList = {
  total: number
  limit: number
  offset: number
  has_more: boolean
  items: CampaignRead[]
}

export type ScrapingStageCounts = {
  badge: number
  total: number
  pending: number
  queued: number
  running: number
  succeeded: number
  failed: number
  retryable_failed: number
  is_live: boolean
}

export type AiReviewStageCounts = {
  badge: number
  all: number
  unclassified: number
  possible: number
  unknown: number
  crap: number
  queued: number
  running: number
  is_live: boolean
}

export type ContactsStageCounts = {
  badge: number
  all: number
  pending: number
  running: number
  done: number
  failed: number
  no_match: number
  contacts_found: number
  emails_found: number
  fetched_people_found: number
  is_live: boolean
}

export type ValidationStageCounts = {
  badge: number
  total: number
  pending: number
  checking: number
  running: number
  stale: number
  valid: number
  undeliverable: number
  catch_all: number
  failed: number
  invalid: number
  unknown: number
  is_live: boolean
}

export type CampaignStageCounts = {
  campaign_id: string
  updated_at: string
  scraping: ScrapingStageCounts
  ai_review: AiReviewStageCounts
  contacts: ContactsStageCounts
  validation: ValidationStageCounts
}

export type CampaignCreate = {
  name: string
  description?: string | null
}

type CompanyStage = 'uploaded' | 'scraped' | 'classified' | 'contact_ready'
export type CompanyStageFilter = 'all' | CompanyStage | 'has_scrape'

export type CompanyListItem = {
  id: string
  upload_id: string
  upload_filename: string
  raw_url: string
  normalized_url: string
  domain: string
  pipeline_stage: CompanyStage
  created_at: string
  last_activity: string
  latest_decision: string | null
  latest_confidence: number | null
  latest_scrape_job_id: string | null
  latest_scrape_status: string | null
  latest_scrape_terminal: boolean | null
  latest_analysis_pipeline_run_id: string | null
  latest_analysis_job_id: string | null
  latest_analysis_status: string | null
  latest_analysis_terminal: boolean | null
  feedback_thumbs: 'up' | 'down' | null
  feedback_comment: string | null
  feedback_manual_label: 'possible' | 'unknown' | 'crap' | null
  latest_scrape_error_code: string | null
  latest_scrape_failure_reason: string | null
  contact_count: number
  discovered_contact_count: number
  discovered_title_matched_count: number
  revealed_contact_count: number
  revealed_title_matched_count: number
  contact_fetch_status: string | null
}

export type ManualLabel = 'possible' | 'unknown' | 'crap'

export type FeedbackUpsert = {
  thumbs?: 'up' | 'down' | null
  comment?: string | null
  manual_label?: ManualLabel | null
}

export type FeedbackRead = {
  thumbs: 'up' | 'down' | null
  comment: string | null
  manual_label: ManualLabel | null
  updated_at: string
}

export type CompanyList = {
  total: number | null
  has_more: boolean
  limit: number
  offset: number
  items: CompanyListItem[]
}

export type DecisionFilter = 'all' | 'unlabeled' | 'possible' | 'unknown' | 'crap' | 'labeled'
export type ScrapeFilter =
  | 'all'
  | 'done'
  | 'failed'
  | 'none'
  | 'not-started'
  | 'in-progress'
  | 'cancelled'
  | 'permanent'
  | 'soft'
export type ScrapeSubFilter =
  | 'all'
  | 'not-started'
  | 'in-progress'
  | 'done'
  | 'cancelled'
  | 'permanent'
  | 'soft'
  | 'pending'
  | 'active'
  | 'failed'

export type CompanyIdsResult = {
  ids: string[]
  total: number
}

export type CompanyScrapeResult = {
  requested_count: number
  queued_count: number
  queued_job_ids: string[]
  failed_company_ids: string[]
  skipped_count?: number
  queue_depth?: number
  idempotency_key?: string | null
  idempotency_replayed?: boolean
}

export type ScrapeRunRead = {
  id: string
  status: string
  requested_count: number
  queued_count: number
  skipped_count: number
  failed_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type ScrapeJobRead = {
  id: string
  website_url: string
  normalized_url: string
  domain: string
  state: string
  status?: string
  terminal_state: boolean
  js_fallback: boolean
  include_sitemap: boolean
  general_model: string
  classify_model: string
  discovered_urls_count: number
  pages_fetched_count: number
  fetch_failures_count: number
  markdown_pages_count: number
  llm_used_count: number
  llm_failed_count: number
  last_error_code: string | null
  last_error_message: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  effective_page_plan_count?: number | null
  effective_page_plan_json?: Array<Record<string, string>> | null
}

export type ScrapeJobCreate = {
  website_url: string
  js_fallback?: boolean
  include_sitemap?: boolean
  general_model?: string
  classify_model?: string
  scrape_rules?: ScrapeRules
}

export type ScrapeRules = {
  classifier_prompt_text?: string | null
  fallback_enabled?: boolean
  fallback_limit?: number
  js_fallback?: boolean | null
  include_sitemap?: boolean | null
}

export type ScrapePageContentRead = {
  id: number
  job_id: string
  url: string
  page_kind: string
  status_code: number
  markdown_content: string
  fetch_error_code: string | null
  fetch_error_message: string | null
  updated_at: string
}

export type PromptRead = {
  id: string
  name: string
  enabled: boolean
  prompt_text: string
  created_at: string
  run_count: number
}

export type PromptCreate = {
  name: string
  prompt_text: string
  enabled?: boolean
}

export type PromptUpdate = {
  name?: string
  prompt_text?: string
  enabled?: boolean
}

export type ScrapePromptRead = {
  id: string
  name: string
  enabled: boolean
  is_system_default: boolean
  is_active: boolean
  intent_text: string | null
  compiled_prompt_text: string
  scrape_rules_structured: ScrapeRules | null
  created_at: string
  updated_at: string
}

export type ScrapePromptCreate = {
  name: string
  intent_text?: string | null
  enabled?: boolean
  set_active?: boolean
}

export type ScrapePromptUpdate = {
  name?: string
  intent_text?: string | null
  enabled?: boolean
}

export type RunRead = {
  id: string
  upload_id: string
  prompt_id: string
  prompt_name: string
  general_model: string
  classify_model: string
  status: string
  total_jobs: number
  completed_jobs: number
  failed_jobs: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type RunCreateRequest = {
  campaign_id: string
  prompt_id: string
  scope: 'all' | 'selected'
  company_ids?: string[]
  general_model?: string
  classify_model?: string
}

export type RunCreateResult = {
  requested_count: number
  queued_count: number
  skipped_company_ids: string[]
  runs: RunRead[]
}

export type PipelineRunStartRequest = {
  campaign_id: string
  company_ids?: string[]
  scrape_rules_snapshot?: Record<string, unknown> | null
  analysis_prompt_snapshot?: Record<string, unknown> | null
  contact_rules_snapshot?: Record<string, unknown> | null
  validation_policy_snapshot?: Record<string, unknown> | null
  force_rerun?: Record<string, boolean> | null
}

export type PipelineRunStartResponse = {
  pipeline_run_id: string
  requested_count: number
  reused_count: number
  queued_count: number
  skipped_count: number
  failed_count: number
}

type PipelineStageProgressRead = {
  queued: number
  running: number
  succeeded: number
  failed: number
  total: number
}

export type PipelineRunProgressRead = {
  pipeline_run_id: string
  campaign_id: string
  state: string
  requested_count: number
  reused_count: number
  queued_count: number
  skipped_count: number
  failed_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  stages: Record<string, PipelineStageProgressRead>
}

type PipelineStageCostRead = {
  cost_usd: number | string
  event_count: number
  input_tokens: number
  output_tokens: number
}

export type PipelineCostSummaryRead = {
  pipeline_run_id: string | null
  campaign_id: string | null
  company_id: string | null
  total_cost_usd: number | string
  event_count: number
  input_tokens: number
  output_tokens: number
  by_stage: Record<string, PipelineStageCostRead>
}

export type AnalysisPipelineJobRead = {
  analysis_job_id: string
  pipeline_run_id: string | null
  company_id: string
  domain: string
  state: string
  terminal_state: boolean
  last_error_code: string | null
  last_error_message: string | null
  predicted_label: string | null
  confidence: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type AnalysisRunJobRead = AnalysisPipelineJobRead

export type PipelineStageStats = {
  total: number
  succeeded: number
  failed: number
  site_unavailable: number
  running: number
  queued: number
  stuck_count: number
  pct_done: number
  avg_job_sec: number | null
  eta_seconds: number | null
  eta_at: string | null
}

export type StatsResponse = {
  scrape: PipelineStageStats
  analysis: PipelineStageStats
  contact_fetch?: PipelineStageStats
  validation?: PipelineStageStats
  costs?: {
    currency: string
    window_days: number
    totals: StageCostTotals
  } | null
  as_of: string
}

type StageCostTotals = {
  scrape: number | null
  analysis: number | null
  contact_fetch: number | null
  validation: number | null
  overall: number | null
}

export type CostLineItem = {
  company_id: string
  domain: string
  scrape: number | null
  analysis: number | null
  contact_fetch: number | null
  validation: number | null
  overall: number | null
}

export type CostStatsResponse = {
  currency: string
  window_days: number
  totals: StageCostTotals
  total: number
  has_more: boolean
  limit: number
  offset: number
  items: CostLineItem[]
}

export type DrainQueueResult = {
  cancelled_scrape_jobs: number
  cancelled_analysis_jobs: number
}

export type CompanyCounts = {
  total: number
  scrape_not_started: number
  scrape_in_progress: number
  scrape_cancelled: number
  scrape_permanent_fail: number
  scrape_soft_fail: number
  uploaded: number
  scraped: number
  classified: number
  contact_ready: number
  unlabeled: number
  possible: number
  unknown: number
  crap: number
  scrape_done: number
  scrape_failed: number
  not_scraped: number
}

export type ResetStuckResult = {
  reset_count: number
}

export type LetterCounts = {
  counts: Record<string, number>
}

// ── S1 Scraping ─────────────────────────────────────────────────────────────

export type ScrapeBatchRead = {
  id: string
  campaign_id: string
  state: string  // 'queued' | 'dispatching' | 'running' | 'completed' | 'failed'
  selected_domain_count: number
  queued_count: number
  success_count: number
  failed_count: number
  created_at: string
  finished_at: string | null
  eta_seconds: number | null
}

export type ScrapeBatchCreate = {
  campaign_id: string
  domain_ids?: string[]
  filter?: {
    scrape_status?: string
    letter?: string
  }
}

export type ScrapeBatchList = {
  total: number
  items: ScrapeBatchRead[]
}

export type ScrapeJobStatusRead = {
  batch_id: string
  campaign_id: string
  state: string
  selected: number
  queued: number
  running: number
  succeeded: number
  failed: number
  terminal: number
  queue_todo: number
  queue_doing: number
  queue_succeeded: number
  queue_failed: number
  queue_cancelled: number
  queue_aborting: number
  queue_aborted: number
  eta_seconds: number | null
  inconsistency_reason: string | null
  created_at: string
  finished_at: string | null
}

export type ScrapeSettingsRead = {
  id: string
  campaign_id: string | null
  name: string
  instruction_text: string | null
  structured_rules_json: Record<string, unknown> | null
  is_active: boolean
  created_at: string
}

export type ScrapeSettingsList = {
  total: number
  items: ScrapeSettingsRead[]
}

export type DecisionModelId =
  | 'inclusionai/ring-2.6-1t'
  | 'ibm-granite/granite-4.1-8b'
  | 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free'
  | 'deepseek/deepseek-v4-flash'
  | 'inclusionai/ling-2.6-1t'
  | 'google/gemma-4-26b-a4b-it:free'
  | 'google/gemma-4-31b-it:free'

export type DecisionSettingsRead = {
  id: string
  campaign_id: string
  name: string
  instruction_text: string
  model: DecisionModelId
  settings_hash: string
  is_active: boolean
  created_at: string
}

export type DecisionSettingsList = {
  total: number
  items: DecisionSettingsRead[]
}

export type DecisionSettingsCreate = {
  campaign_id: string
  name: string
  instruction_text: string
  model: DecisionModelId
  is_active?: boolean
}

export type DecisionSettingsUpdate = {
  name?: string
  instruction_text?: string
  model?: DecisionModelId
  is_active?: boolean
}

export type ScrapeSettingsUpdate = {
  name?: string | null
  instruction_text?: string | null
  structured_rules_json?: Record<string, unknown> | null
  is_active?: boolean | null
}

export type ScrapeResultRead = {
  id: string
  campaign_id: string
  domain_id: string
  scrape_batch_id: string | null
  state: string
  pages_attempted_count: number
  pages_success_count: number
  markdown_pages_count: number
  scraped_pages_json: Array<{
    kind: string
    url: string
    fetch_mode: string
    success: boolean
    status_code: number
    error_code: string | null
    markdown?: string
  }> | null
  error_code: string | null
  failure_class: string | null
  retryable: boolean | null
  final_url: string | null
  created_at: string
  updated_at: string
}

export type DomainLetterCounts = {
  counts: Record<string, number>
}

export type DomainScrapeCounts = {
  total: number
  pending: number
  queued: number
  running: number
  succeeded: number
  failed: number
  retryable_failed: number
  remaining_work: number
}

export type AnalysisJobDetailRead = {
  analysis_job_id: string
  pipeline_run_id: string | null
  company_id: string
  domain: string
  state: string
  terminal_state: boolean
  last_error_code: string | null
  last_error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  prompt_name: string
  pipeline_run_state: string | null
  predicted_label: string | null
  confidence: number | null
  reasoning_json: Record<string, unknown> | null
  evidence_json: Record<string, unknown> | null
}

export type OperationsEventKind = 'scrape' | 'analysis'
export type OperationsEventStatus = 'active' | 'completed' | 'failed'

export type OperationsEvent = {
  id: string
  kind: OperationsEventKind
  status: OperationsEventStatus
  occurred_at: string
  title: string
  subtitle: string
  error_code: string | null
  search_blob: string
  scrape_job: ScrapeJobRead | null
  run: RunRead | null
}

export type ProspectContactRead = {
  id: string
  company_id: string
  contact_fetch_job_id: string
  domain: string
  source_provider: string
  first_name: string
  last_name: string
  title: string | null
  title_match: boolean
  linkedin_url: string | null
  email: string | null
  emails?: string[] | null
  pipeline_stage: ContactStage
  provider_email_status: string | null
  verification_status: string
  snov_confidence: number | null
  provider_has_email: boolean | null
  last_seen_at: string | null
  created_at: string
  updated_at: string
}

export type ContactStage = 'fetched' | 'fetched_no_email' | 'email_revealed' | 'campaign_ready'
export type ContactStageFilter = 'all' | ContactStage

export type ContactListResponse = {
  total: number
  has_more: boolean
  limit: number
  offset: number
  items: ProspectContactRead[]
  letter_counts?: Record<string, number>
}

export type MatchGapFilter = 'all' | 'contacts_no_match' | 'matched_no_email' | 'ready_candidates'

export type TitleMatchRuleRead = {
  id: string
  campaign_id?: string | null
  rule_type: 'include' | 'exclude'
  match_type: 'keyword' | 'regex' | 'seniority'
  keywords: string
  created_at: string
}

export type TitleMatchRuleCreate = {
  campaign_id: string
  rule_type: 'include' | 'exclude'
  keywords: string
  match_type?: 'keyword' | 'regex' | 'seniority'
}

export type TitleTestResult = {
  matched: boolean
  matching_rules: string[]
  excluded_by: string[]
  normalized_title: string
}

type TitleRuleStatItem = {
  rule_id: string
  rule_type: string
  keywords: string
  contact_match_count: number
}

export type TitleRuleStatsResponse = {
  rules: TitleRuleStatItem[]
  total_contacts: number
  total_matched: number
}

export type TitleRuleSeedResult = {
  inserted: number
  message: string
}

export type IntegrationProviderId = 'openrouter' | 'snov' | 'apollo' | 'zerobounce'
type CredentialSource = 'db' | 'env' | ''

export type IntegrationFieldStatus = {
  field: string
  is_set: boolean
  source: CredentialSource
  last4: string | null
  updated_at: string | null
}

export type IntegrationProviderStatus = {
  provider: IntegrationProviderId
  label: string
  description: string
  fields: IntegrationFieldStatus[]
}

export type IntegrationsStatusResponse = {
  store_available: boolean
  providers: IntegrationProviderStatus[]
}

type IntegrationFieldUpdate = {
  field: string
  value: string
}

export type IntegrationProviderUpdateRequest = {
  fields: IntegrationFieldUpdate[]
}

export type IntegrationTestResponse = {
  provider: IntegrationProviderId
  ok: boolean
  source: CredentialSource
  error_code: string
  message: string
}

export type IntegrationHealthItem = {
  provider: string
  label: string
  connected: boolean
  credits_remaining: number | null
  error_code: string
  message: string
}

export type QueueHistoryItem = {
  id: string
  stage: 's1' | 's2' | 's3' | 's4'
  company_domain: string | null
  state: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  error_code: string | null
}

export type QueueHistoryResponse = {
  items: QueueHistoryItem[]
  total: number
}
