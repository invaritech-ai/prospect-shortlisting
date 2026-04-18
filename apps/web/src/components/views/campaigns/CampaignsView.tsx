import { useMemo, useState } from 'react'
import type { CampaignRead, UploadRead } from '../../../lib/types'

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
}: CampaignsViewProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedUploadIds, setSelectedUploadIds] = useState<string[]>([])

  const unassignedUploads = useMemo(
    () => uploads.filter((u) => !u.campaign_id),
    [uploads],
  )

  return (
    <div className="space-y-6">
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
                        onClick={() => onDeleteCampaign(campaign.id)}
                        className="rounded-lg border border-rose-300 px-2 py-1 text-xs text-rose-700"
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
    </div>
  )
}
