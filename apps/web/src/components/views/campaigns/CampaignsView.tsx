import { useState } from 'react'
import type { CampaignRead } from '../../../lib/types'
import type { CampaignPipelineSummary } from '../../../lib/useAppData'
import { CampaignCard }  from './CampaignCard'
import { EmptyState }    from './EmptyState'
import { CampaignPanel } from '../../panels/CampaignPanel'
import { ConfirmDialog } from '../../ui/ConfirmDialog'

function summaryFromCampaign(c: CampaignRead): CampaignPipelineSummary {
  return {
    total: c.company_count,
    notScraped: Math.max(0, c.company_count - c.scrape_count),
    scraped: c.scrape_count,
    classified: c.classified_count,
    possible: c.possible_count,
    contactsFound: c.contact_count,
    validEmails: c.valid_email_count,
    lastActivity: c.updated_at,
  }
}

interface CampaignsViewProps {
  campaigns: CampaignRead[]
  selectedCampaignId: string | null
  onSelectCampaign: (id: string) => void
  onNavigateToDashboard: () => void
  onCreate: (name: string, description: string) => Promise<void> | void
  onEdit: (id: string, name: string, description: string) => Promise<void> | void
  onDelete: (id: string) => Promise<void> | void
}

export function CampaignsView({
  campaigns,
  selectedCampaignId,
  onSelectCampaign,
  onNavigateToDashboard,
  onCreate,
  onEdit,
  onDelete,
}: CampaignsViewProps) {

  const [panelOpen, setPanelOpen]       = useState(false)
  const [editTarget, setEditTarget]     = useState<CampaignRead | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<CampaignRead | null>(null)
  const [isDeleting, setIsDeleting]     = useState(false)

  function openCreate() { setEditTarget(null); setPanelOpen(true) }
  function openEdit(c: CampaignRead) { setEditTarget(c); setPanelOpen(true) }

  async function handleSave(name: string, description: string) {
    if (editTarget) {
      await onEdit(editTarget.id, name, description)
    } else {
      await onCreate(name, description)
    }
  }

  async function handleConfirmDelete() {
    if (!deleteTarget) return
    setIsDeleting(true)
    try { await onDelete(deleteTarget.id) }
    finally { setIsDeleting(false); setDeleteTarget(null) }
  }

  function handleOpen(campaign: CampaignRead) {
    onSelectCampaign(campaign.id)
    onNavigateToDashboard()
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <h1 className="oc-heading-page" style={{ margin: 0 }}>Campaigns</h1>
            <p style={{ fontSize: '0.9375rem', color: 'var(--oc-muted)', marginTop: '0.375rem', maxWidth: '40rem' }}>
              Each campaign is an independent batch of companies moving through the pipeline.
            </p>
          </div>
          <button type="button" onClick={openCreate} className="oc-btn oc-btn-primary oc-btn-md" style={{ flexShrink: 0 }}>
            + New campaign
          </button>
        </div>

        {/* Grid or empty state */}
        {campaigns.length === 0 ? (
          <EmptyState onCreateCampaign={openCreate} />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {campaigns.map((c) => (
              <CampaignCard
                key={c.id}
                campaign={c}
                summary={summaryFromCampaign(c)}
                isActive={c.id === selectedCampaignId}
                onOpen={() => handleOpen(c)}
                onEdit={() => openEdit(c)}
                onDelete={() => setDeleteTarget(c)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create / edit panel */}
      <CampaignPanel
        isOpen={panelOpen}
        onClose={() => setPanelOpen(false)}
        editing={editTarget}
        onSave={handleSave}
      />

      {/* Delete confirmation */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete "${deleteTarget?.name}"?`}
        confirmLabel="Delete campaign"
        confirmVariant="danger"
        isConfirming={isDeleting}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      >
        This permanently removes the campaign and all its data. It cannot be undone.
      </ConfirmDialog>
    </>
  )
}
