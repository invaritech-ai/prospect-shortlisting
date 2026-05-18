import { useState } from 'react'
import type { CampaignRead } from '../../../lib/types'
import { MOCK_CAMPAIGNS, MOCK_RECENT_UPLOADS } from '../../../lib/useAppData'
import { DropZone }       from './DropZone'
import type { DropZoneState } from './DropZone'
import { FormatGuide }    from './FormatGuide'
import { RecentImports }  from './RecentImports'
import { UploadProgress } from './UploadProgress'

type UploadStatus = 'idle' | 'uploading' | 'success'

interface ImportViewProps {
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onUpload: (file: File, campaignId: string) => Promise<void>
  onNavigateToPipeline: () => void
}

/** Rough row estimate from file size — replaced by real parse on the backend. */
function estimateRows(file: File): number {
  const ext = file.name.split('.').pop()?.toLowerCase()
  const bytesPerRow = ext === 'xlsx' || ext === 'xls' ? 80 : 45
  return Math.max(1, Math.round(file.size / bytesPerRow))
}

export function ImportView({
  campaigns: rawCampaigns,
  selectedCampaignId,
  onUpload,
  onNavigateToPipeline,
}: ImportViewProps) {
  const campaigns = rawCampaigns.length ? rawCampaigns : MOCK_CAMPAIGNS

  const [file, setFile]                 = useState<File | null>(null)
  const [dropState, setDropState]       = useState<DropZoneState>('idle')
  const [campaignId, setCampaignId]     = useState(selectedCampaignId ?? campaigns[0]?.id ?? '')
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [uploadedRows, setUploadedRows] = useState<number | null>(null)

  function handleFileChange(f: File | null) {
    setFile(f)
    setDropState(f ? 'selected' : 'idle')
    setUploadStatus('idle')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !campaignId) return
    const rows = estimateRows(file)
    setUploadStatus('uploading')
    try {
      await onUpload(file, campaignId)
    } catch {
      // real error handling wired later
    }
    // Simulate processing delay for mock
    await new Promise((r) => setTimeout(r, 1800))
    setUploadedRows(rows)
    setUploadStatus('success')
  }

  function handleDone() {
    setFile(null)
    setDropState('idle')
    setUploadStatus('idle')
    setUploadedRows(null)
    if (uploadStatus === 'success') onNavigateToPipeline()
  }

  const canSubmit = Boolean(file && campaignId && uploadStatus === 'idle')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '860px' }}>

      {/* Header */}
      <div>
        <h1 className="oc-heading-page" style={{ margin: 0 }}>Import Companies</h1>
        <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginTop: '0.375rem' }}>
          Upload a spreadsheet of company URLs. We'll scrape, classify, and find contacts automatically.
        </p>
      </div>

      {/* Show progress/success OR the upload form */}
      {uploadStatus !== 'idle' ? (
        <UploadProgress
          status={uploadStatus}
          filename={file?.name ?? ''}
          rowCount={uploadedRows ?? undefined}
          onDone={handleDone}
        />
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

          {/* Two-column on desktop: drop zone + format guide */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}
            className="md:grid-cols-[1fr_320px]"
          >
            <DropZone
              file={file}
              state={dropState}
              estimatedRows={file ? estimateRows(file) : null}
              onFileChange={handleFileChange}
              onDragStateChange={(d) => setDropState(d ? 'dragging' : file ? 'selected' : 'idle')}
            />
            <FormatGuide />
          </div>

          {/* Campaign assignment */}
          <div className="oc-form-field">
            <label htmlFor="campaign-select" className="oc-form-label">
              Assign to campaign
            </label>
            <select
              id="campaign-select"
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
              className="oc-select"
            >
              <option value="" disabled>Select a campaign…</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <p className="oc-form-hint">
              Companies will be added to this campaign's pipeline.
            </p>
          </div>

          {/* Upload CTA — full width, large, prominent */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="oc-btn oc-btn-primary"
            style={{
              width: '100%',
              padding: '1rem',
              fontSize: '1.0625rem',
              fontWeight: 700,
              borderRadius: '0.875rem',
              minHeight: '56px', /* large touch target */
              justifyContent: 'center',
              opacity: canSubmit ? 1 : 0.4,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
            }}
          >
            {file ? `Upload ${file.name}` : 'Select a file to upload'}
          </button>

        </form>
      )}

      {/* Recent imports */}
      <RecentImports uploads={MOCK_RECENT_UPLOADS} campaigns={campaigns} />

    </div>
  )
}
