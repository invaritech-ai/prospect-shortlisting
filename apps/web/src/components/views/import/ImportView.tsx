import { useState } from 'react'
import type { CampaignRead, UploadRead } from '../../../lib/types'
import { DropZone }       from './DropZone'
import type { DropZoneState } from './DropZone'
import { FormatGuide }    from './FormatGuide'
import { RecentImports }  from './RecentImports'
import { UploadProgress } from './UploadProgress'

type UploadStatus = 'idle' | 'uploading' | 'success'

interface ImportViewProps {
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  uploads: UploadRead[]
  onUpload: (file: File, campaignId: string) => Promise<{ new_count: number; dupe_count: number }>
  onNavigateToPipeline: () => void
}

export function ImportView({
  campaigns,
  selectedCampaignId,
  uploads,
  onUpload,
  onNavigateToPipeline,
}: ImportViewProps) {
  const [file, setFile]                 = useState<File | null>(null)
  const [dropState, setDropState]       = useState<DropZoneState>('idle')
  const [campaignId, setCampaignId]     = useState(selectedCampaignId ?? campaigns[0]?.id ?? '')
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [newCount, setNewCount]         = useState<number | null>(null)

  function handleFileChange(f: File | null) {
    setFile(f)
    setDropState(f ? 'selected' : 'idle')
    setUploadStatus('idle')
    setNewCount(null)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !campaignId) return
    setUploadStatus('uploading')
    try {
      const result = await onUpload(file, campaignId)
      setNewCount(result.new_count)
      setUploadStatus('success')
    } catch {
      setUploadStatus('idle')
    }
  }

  function handleDone() {
    setFile(null)
    setDropState('idle')
    setUploadStatus('idle')
    setNewCount(null)
    if (uploadStatus === 'success') onNavigateToPipeline()
  }

  const canSubmit = Boolean(file && campaignId && uploadStatus === 'idle')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>

      {/* ── Page header — matches FullPipelineView / DashboardView pattern ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem', flexWrap: 'wrap' }}>
        <span style={{
          width: '7px', height: '7px', borderRadius: '2px',
          backgroundColor: 'var(--oc-accent)', flexShrink: 0,
        }} />
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: '1.5rem',
          color: 'var(--oc-accent)', margin: 0, lineHeight: 1, letterSpacing: '-0.015em',
        }}>
          Upload Companies
        </h1>
        <span style={{ fontSize: '0.875rem', color: 'var(--oc-muted)', fontWeight: 500 }}>
          · spreadsheet → pipeline
        </span>
      </div>

      {/* ── Upload form or progress ── */}
      {uploadStatus !== 'idle' ? (
        <UploadProgress
          status={uploadStatus}
          filename={file?.name ?? ''}
          rowCount={newCount ?? undefined}
          onDone={handleDone}
        />
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

          {/* Drop zone */}
          <DropZone
            file={file}
            state={dropState}
            estimatedRows={null}
            onFileChange={handleFileChange}
            onDragStateChange={(d) => setDropState(d ? 'dragging' : file ? 'selected' : 'idle')}
          />

          {/* Format guide — collapsible, sits below drop zone */}
          <FormatGuide />

          {/* Campaign assignment */}
          <div className="oc-panel" style={{ padding: '1.125rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.875rem' }}>
            <div className="oc-form-field" style={{ margin: 0 }}>
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
          </div>

          {/* Upload CTA */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="oc-btn oc-btn-primary oc-btn-md"
            style={{
              width: '100%',
              justifyContent: 'center',
              minHeight: '52px',
              fontSize: '1rem',
              opacity: canSubmit ? 1 : 0.4,
              cursor: canSubmit ? 'pointer' : 'not-allowed',
            }}
          >
            {file ? `Upload ${file.name}` : 'Select a file to upload'}
          </button>

        </form>
      )}

      {/* ── Recent uploads ── */}
      <RecentImports uploads={uploads} campaigns={campaigns} />

    </div>
  )
}
