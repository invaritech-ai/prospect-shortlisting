import { useMemo, useState } from 'react'
import type { CampaignRead, PipelineCostSummaryRead, PipelineRunProgressRead, UploadRead } from '../../../lib/types'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

interface CampaignsViewProps {
  campaigns: CampaignRead[]
  uploads: UploadRead[]
  selectedCampaignId: string | null
  isLoading: boolean
  isSaving: boolean
  onSelectCampaign: (campaignId: string | null) => void
  onCreateCampaign: (name: string, description: string) => void
  onDeleteCampaign: (campaignId: string) => void
  onAssignUploads: (campaignId: string, uploadIds: string[]) => void
  onStartCampaignPipeline: () => void
  onOpenFullPipeline: () => void
  isStartingCampaignPipeline: boolean
  latestRunProgress: PipelineRunProgressRead | null
  campaignCostSummary: PipelineCostSummaryRead | null
}

export function CampaignsView({
  campaigns,
  uploads,
  selectedCampaignId,
  isLoading,
  isSaving,
  onSelectCampaign,
  onCreateCampaign,
  onDeleteCampaign,
  onAssignUploads,
  onStartCampaignPipeline,
  onOpenFullPipeline,
  isStartingCampaignPipeline,
  latestRunProgress,
  campaignCostSummary,
}: CampaignsViewProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedUploadIds, setSelectedUploadIds] = useState<string[]>([])
  const [pendingDeleteCampaignId, setPendingDeleteCampaignId] = useState<string | null>(null)
  const selectedCampaign = useMemo(
    () => campaigns.find((campaign) => campaign.id === selectedCampaignId) ?? null,
    [campaigns, selectedCampaignId],
  )

  const unassignedUploads = useMemo(
    () => uploads.filter((u) => !u.campaign_id),
    [uploads],
  )

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-(--oc-muted)">Campaign Workspace</h2>
        <p className="mt-1 text-xs text-(--oc-muted)">
          Campaign-level controls only. Detailed domain cost breakdown lives in Operations.
        </p>
        {!selectedCampaignId ? (
          <p className="mt-2 text-sm text-(--oc-muted)">Select a campaign to start pipeline and track live progress.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {selectedCampaign && (
              <div className="rounded-xl border border-(--oc-border) bg-white p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-(--oc-muted)">Selected campaign</p>
                    <p className="text-sm font-semibold text-(--oc-text)">{selectedCampaign.name}</p>
                    <p className="text-xs text-(--oc-muted)">{selectedCampaign.description || 'No description'}</p>
                  </div>
                  {campaignCostSummary && (
                    <span className="rounded-full border border-(--oc-border) bg-(--oc-surface) px-3 py-1 text-xs font-semibold text-(--oc-muted)">
                      Campaign spend: ${Number(campaignCostSummary.total_cost_usd || 0).toFixed(4)}
                    </span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="rounded-lg border border-(--oc-border) bg-(--oc-surface) px-2.5 py-1 text-(--oc-muted)">
                    Domains in campaign: {selectedCampaign.company_count.toLocaleString()}
                  </span>
                  <span className="rounded-lg border border-(--oc-border) bg-(--oc-surface) px-2.5 py-1 text-(--oc-muted)">
                    Files attached: {selectedCampaign.upload_count.toLocaleString()}
                  </span>
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isStartingCampaignPipeline}
                onClick={onStartCampaignPipeline}
                className="rounded-xl bg-(--oc-accent) px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
              >
                {isStartingCampaignPipeline ? 'Queueing pipeline…' : 'Start pipeline'}
              </button>
              <button
                type="button"
                onClick={onOpenFullPipeline}
                className="rounded-xl border border-(--oc-border) bg-white px-4 py-2 text-sm font-semibold text-(--oc-accent-ink) transition hover:border-(--oc-accent)"
              >
                Open Full Pipeline
              </button>
            </div>
            {latestRunProgress && (
              <div className="space-y-2 rounded-xl border border-(--oc-border) bg-white p-3">
                <p className="text-xs font-semibold text-(--oc-text)">
                  Latest run status: {latestRunProgress.state}
                </p>
                {Object.entries(latestRunProgress.stages).map(([stage, counts]) => {
                  const total = Math.max(1, counts.total)
                  const done = counts.succeeded + counts.failed
                  const pct = Math.min(100, Math.round((done / total) * 100))
                  return (
                    <div key={stage} className="space-y-1">
                      <div className="flex items-center justify-between text-[11px] text-(--oc-muted)">
                        <span>{stage}</span>
                        <span>{counts.running} running · {counts.succeeded} done · {counts.failed} failed</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-(--oc-surface)">
                        <div className="h-full rounded-full bg-(--oc-accent)" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-(--oc-muted)">Create Campaign</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-[1fr_2fr_auto]">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Campaign name"
            className="rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none focus:border-(--oc-accent)"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none focus:border-(--oc-accent)"
          />
          <button
            type="button"
            disabled={isSaving || !name.trim()}
            onClick={() => {
              onCreateCampaign(name.trim(), description.trim())
              setName('')
              setDescription('')
            }}
            className="rounded-xl bg-(--oc-accent) px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            Create
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wider text-(--oc-muted)">Campaigns</h2>
          <button
            type="button"
            onClick={() => onSelectCampaign(null)}
            className="rounded-lg border border-(--oc-border) px-2 py-1 text-xs text-(--oc-muted)"
          >
            Clear selection
          </button>
        </div>
        {isLoading ? (
          <p className="text-sm text-(--oc-muted)">Loading campaigns...</p>
        ) : campaigns.length === 0 ? (
          <p className="text-sm text-(--oc-muted)">No campaigns yet.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {campaigns.map((campaign) => {
              const isSelected = selectedCampaignId === campaign.id
              return (
                <div
                  key={campaign.id}
                  className={`rounded-xl border p-3 ${isSelected ? 'border-(--oc-accent)' : 'border-(--oc-border)'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-bold text-(--oc-text)">{campaign.name}</h3>
                      <p className="mt-1 text-xs text-(--oc-muted)">{campaign.description || 'No description'}</p>
                      <p className="mt-2 text-xs text-(--oc-muted)">
                        {campaign.upload_count} uploads · {campaign.company_count} companies
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectCampaign(campaign.id)}
                        className="rounded-lg border border-(--oc-border) px-2 py-1 text-xs"
                      >
                        {isSelected ? 'Selected' : 'Use'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setPendingDeleteCampaignId(campaign.id)}
                        disabled={isSaving}
                        className="rounded-lg border border-rose-300 px-2 py-1 text-xs text-rose-700 disabled:opacity-50"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-(--oc-muted)">Assign Existing Uploads</h2>
        {!selectedCampaignId ? (
          <p className="mt-2 text-sm text-(--oc-muted)">Select a campaign first.</p>
        ) : unassignedUploads.length === 0 ? (
          <p className="mt-2 text-sm text-(--oc-muted)">No unassigned uploads.</p>
        ) : (
          <>
            <div className="mt-3 max-h-48 space-y-2 overflow-auto rounded-xl border border-(--oc-border) bg-white p-2">
              {unassignedUploads.map((upload) => {
                const checked = selectedUploadIds.includes(upload.id)
                return (
                  <label key={upload.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        setSelectedUploadIds((prev) =>
                          e.target.checked ? [...prev, upload.id] : prev.filter((id) => id !== upload.id),
                        )
                      }}
                    />
                    <span className="font-medium">{upload.filename}</span>
                    <span className="text-(--oc-muted)">({upload.valid_count} domains)</span>
                  </label>
                )
              })}
            </div>
            <button
              type="button"
              disabled={isSaving || selectedUploadIds.length === 0}
              onClick={() => {
                onAssignUploads(selectedCampaignId, selectedUploadIds)
                setSelectedUploadIds([])
              }}
              className="mt-3 rounded-xl bg-(--oc-accent) px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              Assign Selected Uploads
            </button>
          </>
        )}
      </section>

      <ConfirmDialog
        open={pendingDeleteCampaignId !== null}
        title="Delete campaign?"
        confirmLabel="Delete"
        confirmVariant="danger"
        isConfirming={isSaving}
        onClose={() => setPendingDeleteCampaignId(null)}
        onConfirm={() => {
          if (pendingDeleteCampaignId) {
            onDeleteCampaign(pendingDeleteCampaignId)
            setPendingDeleteCampaignId(null)
          }
        }}
      >
        <p className="text-sm text-(--oc-muted)">
          This will permanently delete the campaign and all associated data. This cannot be undone.
        </p>
      </ConfirmDialog>
    </div>
  )
}
