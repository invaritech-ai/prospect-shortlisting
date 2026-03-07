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
}

export type CompanyList = {
  total: number | null
  has_more: boolean
  limit: number
  offset: number
  items: CompanyListItem[]
}

export type DecisionFilter = 'all' | 'unlabeled' | 'possible' | 'unknown' | 'crap'

export type CompanyDeleteResult = {
  requested_count: number
  deleted_count: number
  deleted_ids: string[]
  missing_ids: string[]
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

export type JobEnqueueResult = {
  job_id: string
  task_id: string
  task_type: string
  queue_key: string
  message: string
}
