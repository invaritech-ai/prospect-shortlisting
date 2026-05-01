type UploadValidationError = {
  row_number: number
  raw_value: string
  error_code: string
  error_message: string
}

export type UploadRead = {
  id: string
  campaign_id: string | null
  filename: string
  checksum: string
  row_count: number
  valid_count: number
  invalid_count: number
  created_at: string
}

export type UploadCreateResult = {
  upload: UploadRead
  validation_errors: UploadValidationError[]
  already_in_campaign_count: number
}

export type UploadList = {
  total: number
  limit: number
  offset: number
  items: UploadRead[]
}

export type CampaignRead = {
  id: string
  name: string
  description: string | null
  upload_count: number
  company_count: number
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
export type S4VerifFilter = 'all' | 'valid' | 'invalid' | 'catch-all' | 'unverified' | 'campaign_ready' | 'title_match' | 'stale_30d'

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
  selected_page_kinds?: ScrapePageKind[] | null
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

export type ScrapePageKind =
  | 'home'
  | 'about'
  | 'products'
  | 'contact'
  | 'team'
  | 'leadership'
  | 'services'
  | 'pricing'

export type ScrapeRules = {
  page_kinds?: ScrapePageKind[]
  classifier_prompt_text?: string | null
  fallback_enabled?: boolean
  fallback_limit?: number
  fallback_priority?: ScrapePageKind[]
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
  contact_reveal?: PipelineStageStats
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

export type ContactStage = 'fetched' | 'email_revealed' | 'campaign_ready'
export type ContactStageFilter = 'all' | ContactStage

export type ContactListResponse = {
  total: number
  has_more: boolean
  limit: number
  offset: number
  items: ProspectContactRead[]
  letter_counts?: Record<string, number>
}

export type ContactFetchResult = {
  requested_count: number
  queued_count: number
  already_fetching_count: number
  queued_job_ids: string[]
  reused_count?: number
  stale_reused_count?: number
  batch_id?: string | null
  idempotency_key?: string | null
  idempotency_replayed?: boolean
}

export type ContactCompanySummary = {
  company_id: string
  domain: string
  total_count: number
  title_matched_count: number
  unmatched_count?: number
  matched_no_email_count?: number
  email_count: number
  fetched_count: number
  verified_count: number
  campaign_ready_count: number
  eligible_verify_count: number
  last_contact_attempted_at?: string | null
}

export type ContactCompanyListResponse = {
  total: number
  has_more: boolean
  limit: number
  offset: number
  items: ContactCompanySummary[]
}

export type ContactCountsResponse = {
  total: number
  fetched: number
  verified: number
  campaign_ready: number
  eligible_verify: number
}

export type ContactVerifyRequest = {
  campaign_id: string
  contact_ids?: string[]
  company_ids?: string[]
  title_match?: boolean
  verification_status?: string
  search?: string
  stage_filter?: ContactStageFilter
}

export type ContactVerifyResult = {
  job_id: string
  selected_count: number
  message: string
  idempotency_key?: string | null
  idempotency_replayed?: boolean
}

export type DiscoveredContactRead = {
  id: string
  company_id: string
  contact_fetch_job_id?: string | null
  domain: string
  source_provider: string
  provider_person_id: string
  first_name: string
  last_name: string
  title: string | null
  title_match: boolean
  linkedin_url: string | null
  source_url: string | null
  provider_has_email: boolean | null
  is_active: boolean
  backfilled: boolean
  freshness_status: 'fresh' | 'stale'
  group_key: string
  discovered_at: string
  last_seen_at: string
  created_at: string
  updated_at: string
}

export type DiscoveredContactListResponse = {
  total: number
  has_more: boolean
  limit: number
  offset: number
  items: DiscoveredContactRead[]
  letter_counts?: Record<string, number>
}

export type DiscoveredContactCountsResponse = {
  total: number
  matched: number
  stale: number
  fresh: number
  already_revealed: number
}

export type DiscoveredContactIdsResult = {
  ids: string[]
  total: number
}

export type ContactRevealRequest = {
  campaign_id: string
  discovered_contact_ids?: string[]
  company_ids?: string[]
}

export type ContactRevealResult = {
  batch_id?: string | null
  selected_count: number
  queued_count: number
  already_revealing_count: number
  skipped_revealed_count: number
  message: string
  idempotency_key?: string | null
  idempotency_replayed?: boolean
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
  stage: 's1' | 's2' | 's3' | 's4' | 's5'
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
