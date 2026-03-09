export type UploadValidationError = {
  row_number: number
  raw_value: string
  error_code: string
  error_message: string
}

export type UploadRead = {
  id: string
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
}

export type UploadDetail = UploadCreateResult

export type UploadList = {
  total: number
  limit: number
  offset: number
  items: UploadRead[]
}

export type CompanyRead = {
  id: string
  upload_id: string
  raw_url: string
  normalized_url: string
  domain: string
  created_at: string
}

export type CompanyListItem = {
  id: string
  upload_id: string
  upload_filename: string
  raw_url: string
  normalized_url: string
  domain: string
  created_at: string
  latest_decision: string | null
  latest_confidence: number | null
  latest_scrape_job_id: string | null
  latest_scrape_status: string | null
  latest_scrape_terminal: boolean | null
  latest_scrape_stage1_status: string | null
  latest_scrape_stage2_status: string | null
  latest_analysis_run_id: string | null
  latest_analysis_status: string | null
  latest_analysis_terminal: boolean | null
}

export type CompanyList = {
  total: number | null
  has_more: boolean
  limit: number
  offset: number
  items: CompanyListItem[]
}

export type DecisionFilter = 'all' | 'unlabeled' | 'possible' | 'unknown' | 'crap'
export type ScrapeFilter = 'all' | 'done' | 'failed' | 'none'

export type CompanyIdsResult = {
  ids: string[]
  total: number
}

export type CompanyDeleteResult = {
  requested_count: number
  deleted_count: number
  deleted_ids: string[]
  missing_ids: string[]
}

export type CompanyScrapeResult = {
  requested_count: number
  queued_count: number
  queued_job_ids: string[]
  failed_company_ids: string[]
}

export type UploadCompanyList = {
  upload_id: string
  total: number
  limit: number
  offset: number
  items: CompanyRead[]
}

export type ScrapeJobRead = {
  id: string
  website_url: string
  normalized_url: string
  domain: string
  status: string
  stage1_status: string
  stage2_status: string
  terminal_state: boolean
  max_pages: number
  max_depth: number
  js_fallback: boolean
  include_sitemap: boolean
  general_model: string
  classify_model: string
  ocr_model: string
  enable_ocr: boolean
  max_images_per_page: number
  discovered_urls_count: number
  pages_fetched_count: number
  fetch_failures_count: number
  markdown_pages_count: number
  ocr_images_processed_count: number
  llm_used_count: number
  llm_failed_count: number
  last_error_code: string | null
  last_error_message: string | null
  created_at: string
  updated_at: string
  step1_started_at: string | null
  step1_finished_at: string | null
  step2_started_at: string | null
  step2_finished_at: string | null
}

export type ScrapeJobCreate = {
  website_url: string
  max_pages?: number
  max_depth?: number
  js_fallback?: boolean
  include_sitemap?: boolean
  general_model?: string
  classify_model?: string
  ocr_model?: string
  enable_ocr?: boolean
  max_images_per_page?: number
}

export type ScrapePageContentRead = {
  id: number
  job_id: string
  url: string
  page_kind: string
  status_code: number
  screenshot_path: string
  screenshot_exists: boolean
  markdown_content: string
  ocr_text: string
  fetch_error_code: string
  fetch_error_message: string
  updated_at: string
}

export type JobEnqueueResult = {
  job_id: string
  task_id: string
  task_type: string
  queue_key: string
  message: string
}

export type PromptRead = {
  id: string
  name: string
  enabled: boolean
  prompt_text: string
  created_at: string
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

export type RunRead = {
  id: string
  upload_id: string
  prompt_id: string
  prompt_name: string
  general_model: string
  classify_model: string
  ocr_model: string
  status: string
  total_jobs: number
  completed_jobs: number
  failed_jobs: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type RunCreateRequest = {
  prompt_id: string
  scope: 'all' | 'selected'
  company_ids?: string[]
  general_model?: string
  classify_model?: string
  ocr_model?: string
}

export type RunCreateResult = {
  requested_count: number
  queued_count: number
  skipped_company_ids: string[]
  runs: RunRead[]
}

export type AnalysisRunJobRead = {
  analysis_job_id: string
  run_id: string
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

export type PipelineStageStats = {
  total: number
  completed: number
  failed: number
  running: number
  queued: number
  pct_done: number
  avg_job_sec: number | null
  eta_seconds: number | null
  eta_at: string | null
}

export type StatsResponse = {
  scrape: PipelineStageStats
  analysis: PipelineStageStats
  as_of: string
}

export type DrainQueueResult = {
  drained: number
  cancelled_db_jobs: number
  queue_key: string
}

export type CompanyCounts = {
  total: number
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

export type AnalysisJobDetailRead = {
  analysis_job_id: string
  run_id: string
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
  run_status: string
  predicted_label: string | null
  confidence: number | null
  reasoning_json: Record<string, unknown> | null
  evidence_json: Record<string, unknown> | null
}
