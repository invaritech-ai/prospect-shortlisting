import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  configureApiSession,
  createCampaign,
  deleteCampaign,
  getCurrentUser,
  getCampaignCosts,
  getIntegrationsHealth,
  loginWithPassword,
  listCampaigns,
  listUploads,
  logoutSession,
  uploadFileToCampaign,
} from './lib/api'
import type {
  CampaignRead,
  IntegrationHealthItem,
  PipelineCostSummaryRead,
  UploadRead,
} from './lib/types'
import { buildRouteSearch, parseRouteState, type ActiveView } from './lib/navigation'
import type { AuthSession } from './lib/auth'
import { parseApiError } from './lib/utils'

// Layout
import { AppShell } from './components/layout/AppShell'

// Views (rebuilt)
import { DashboardView }  from './components/views/pipeline/DashboardView'
import { ScrapingView }   from './components/views/scraping/ScrapingView'
import { AIReviewView }   from './components/views/ai-review/AIReviewView'
import { ContactsView }   from './components/views/contacts/ContactsView'
import { ValidationView } from './components/views/validation/ValidationView'
import { CampaignsView }  from './components/views/campaigns/CampaignsView'
import { ImportView }     from './components/views/import/ImportView'
import { SettingsView }   from './components/views/settings/SettingsView'
import { QueueHistoryView } from './components/views/QueueHistoryView'
import { LoginView }      from './components/views/auth/LoginView'

// UI
import { Toast, type ToastNoticeAction } from './components/ui/Toast'
import { GlobalLoadingOverlay } from './components/ui/GlobalLoadingOverlay'

const INITIAL_ROUTE_STATE = typeof window === 'undefined'
  ? { view: 'dashboard' as ActiveView, campaignId: null as string | null }
  : parseRouteState(window.location.search)
const AUTH_REQUIRED = ((import.meta as { env?: Record<string, string | undefined> }).env?.VITE_AUTH_REQUIRED ?? 'false') === 'true'

function ComingSoon({ label }: { label: string }) {
  return (
    <div className="oc-panel" style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--oc-muted)' }}>
      <p style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>{label}</p>
      <p style={{ fontSize: '0.875rem' }}>Coming soon — being rebuilt against the new schema.</p>
    </div>
  )
}

function App() {
  // ── Navigation ────────────────────────────────────────────────────────────
  const [activeView, setActiveView] = useState<ActiveView>(INITIAL_ROUTE_STATE.view)

  // ── Auth ──────────────────────────────────────────────────────────────────
  const [authSession, setAuthSession] = useState<AuthSession | null>(null)
  const [isAuthBootstrapping, setIsAuthBootstrapping] = useState(AUTH_REQUIRED)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [authError, setAuthError] = useState('')
  const authRequestsEnabled = !AUTH_REQUIRED || (!isAuthBootstrapping && authSession !== null)

  // ── Toasts ────────────────────────────────────────────────────────────────
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeAction, setNoticeAction] = useState<ToastNoticeAction | null>(null)
  const [busyMessage, setBusyMessage] = useState<string | null>(null)

  // ── Campaign + Upload data ────────────────────────────────────────────────
  const [campaigns, setCampaigns] = useState<CampaignRead[]>([])
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(INITIAL_ROUTE_STATE.campaignId)
  const [uploads, setUploads] = useState<UploadRead[]>([])
  const [, setIsCampaignSaving] = useState(false)

  // ── Services health ───────────────────────────────────────────────────────
  const [servicesHealth, setServicesHealth] = useState<IntegrationHealthItem[] | null>(null)
  const [isLoadingHealth, setIsLoadingHealth] = useState(false)

  // ── Campaign costs (for CampaignsView) ───────────────────────────────────
  const [, setCampaignCostSummary] = useState<PipelineCostSummaryRead | null>(null)
  const campaignCostsRouteMissingRef = { current: false }

  const activeCampaignName =
    campaigns.find((c) => c.id === selectedCampaignId)?.name ??
    campaigns[0]?.name ??
    null

  // ── Load functions ────────────────────────────────────────────────────────

  const loadServicesHealth = useCallback(async () => {
    if (!authRequestsEnabled) return
    setIsLoadingHealth(true)
    try {
      setServicesHealth(await getIntegrationsHealth())
    } catch { /* non-critical */ }
    finally { setIsLoadingHealth(false) }
  }, [authRequestsEnabled])

  const loadCampaignData = useCallback(async () => {
    if (!authRequestsEnabled) {
      setCampaigns([])
      setUploads([])
      return
    }
    let activeCampaignId: string | null = selectedCampaignId
    try {
      const rows = await listCampaigns(200, 0)
      setCampaigns(rows.items)
      if (rows.items.length > 0) {
        if (!selectedCampaignId || !rows.items.some((c) => c.id === selectedCampaignId)) {
          const pilot = rows.items.find((c) => c.name.toLowerCase().includes('pilot'))
          activeCampaignId = (pilot ?? rows.items[0]).id
          setSelectedCampaignId(activeCampaignId)
        }
      } else {
        activeCampaignId = null
        if (selectedCampaignId) setSelectedCampaignId(null)
      }
    } catch {
      setCampaigns([])
      activeCampaignId = null
    }
    if (activeCampaignId) {
      listUploads(activeCampaignId, 200, 0).then((r) => setUploads(r.items)).catch(() => setUploads([]))
    } else {
      setUploads([])
    }
  }, [authRequestsEnabled, selectedCampaignId])

  const loadCampaignCostSummary = useCallback(async (campaignId: string | null) => {
    if (!authRequestsEnabled || !campaignId || campaignCostsRouteMissingRef.current) {
      setCampaignCostSummary(null)
      return
    }
    try {
      setCampaignCostSummary(await getCampaignCosts(campaignId))
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) campaignCostsRouteMissingRef.current = true
      setCampaignCostSummary(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequestsEnabled])

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    configureApiSession({
      getAccessToken: () => authSession?.accessToken ?? null,
      onUnauthorized: () => {
        if (!AUTH_REQUIRED || isAuthBootstrapping) return
        setAuthSession(null)
        setAuthError('Your session expired. Please sign in again.')
      },
    })
  }, [authSession, isAuthBootstrapping])

  useEffect(() => {
    if (!AUTH_REQUIRED) { setIsAuthBootstrapping(false); return }
    let cancelled = false
    const bootstrap = async () => {
      try {
        const me = await getCurrentUser()
        if (!cancelled) setAuthSession({ userEmail: me.email, displayName: me.display_name?.trim() || me.email, accessToken: null })
      } catch {
        if (!cancelled) setAuthSession(null)
      } finally {
        if (!cancelled) setIsAuthBootstrapping(false)
      }
    }
    void bootstrap()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!authRequestsEnabled) return
    void loadCampaignData()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authRequestsEnabled])

  useEffect(() => { void loadServicesHealth() }, [loadServicesHealth])

  useEffect(() => {
    setCampaignCostSummary(null)
    void loadCampaignCostSummary(selectedCampaignId)
  }, [selectedCampaignId, loadCampaignCostSummary])

  useEffect(() => {
    if (!error) return
    const t = window.setTimeout(() => setError(''), 5000)
    return () => window.clearTimeout(t)
  }, [error])

  useEffect(() => {
    if (!notice) return
    const t = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  // ── Navigation helpers ────────────────────────────────────────────────────

  const syncUrlState = useCallback((state: { view: ActiveView; campaignId: string | null }, mode: 'push' | 'replace') => {
    if (typeof window === 'undefined') return
    const search = buildRouteSearch({ view: state.view, campaignId: state.campaignId })
    const nextUrl = `${window.location.pathname}${search}${window.location.hash}`
    if (nextUrl === `${window.location.pathname}${window.location.search}${window.location.hash}`) return
    window.history[mode === 'push' ? 'pushState' : 'replaceState']({}, '', nextUrl)
  }, [])

  const navigateToView = useCallback((view: ActiveView) => {
    const viewNeedsCampaign = view !== 'dashboard' && view !== 'campaigns' && view !== 'uploads' && view !== 'settings'
    if (viewNeedsCampaign && !selectedCampaignId) {
      setActiveView('campaigns')
      syncUrlState({ view: 'campaigns', campaignId: selectedCampaignId }, 'push')
      setNotice('Select a campaign first, then continue to the pipeline stage.')
      setNoticeAction({ label: 'Open Campaigns', onClick: () => setActiveView('campaigns') })
      return
    }
    setNoticeAction(null)
    setActiveView(view)
    syncUrlState({ view, campaignId: selectedCampaignId }, 'push')
  }, [selectedCampaignId, syncUrlState])

  const setCampaignFromUser = useCallback((campaignId: string | null) => {
    setSelectedCampaignId(campaignId)
    syncUrlState({ view: activeView, campaignId }, 'push')
  }, [activeView, syncUrlState])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onPopState = () => {
      const state = parseRouteState(window.location.search)
      setActiveView(state.view)
      setSelectedCampaignId(state.campaignId)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    syncUrlState({ view: activeView, campaignId: selectedCampaignId }, 'replace')
  }, [activeView, selectedCampaignId, syncUrlState])

  // ── Actions ───────────────────────────────────────────────────────────────

  const onUploadFromView = async (file: File, campaignId: string): Promise<{ new_count: number; dupe_count: number }> => {
    const result = await uploadFileToCampaign(file, campaignId)
    void loadCampaignData()
    return { new_count: result.new_count, dupe_count: result.dupe_count }
  }

  const onCreateCampaign = async (name: string, description: string) => {
    setIsCampaignSaving(true)
    setBusyMessage('Creating campaign…')
    try {
      const created = await createCampaign({ name, description })
      setSelectedCampaignId(created.id)
      setNotice(`Campaign "${created.name}" created.`)
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setBusyMessage(null)
      setIsCampaignSaving(false)
    }
  }

  const onDeleteCampaign = async (campaignId: string) => {
    setIsCampaignSaving(true)
    setBusyMessage('Deleting campaign…')
    try {
      await deleteCampaign(campaignId)
      if (selectedCampaignId === campaignId) setSelectedCampaignId(null)
      setNotice('Campaign deleted.')
      await loadCampaignData()
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setBusyMessage(null)
      setIsCampaignSaving(false)
    }
  }

  const handleLogin = useCallback(async (email: string, password: string) => {
    if (!email.trim() || !password.trim()) { setAuthError('Email and password are required.'); return }
    setIsSigningIn(true)
    setAuthError('')
    try {
      const response = await loginWithPassword(email.trim(), password)
      setAuthSession({ userEmail: response.user.email, displayName: response.user.display_name?.trim() || response.user.email, accessToken: response.access_token ?? null })
    } catch (err) {
      setAuthError(parseApiError(err))
    } finally {
      setIsSigningIn(false)
    }
  }, [])

  const handleLogout = useCallback(async () => {
    try { await logoutSession() } catch { /* already invalid */ }
    setAuthSession(null)
    setAuthError('')
    setNotice('Signed out.')
    setNoticeAction(null)
  }, [])

  // ── Auth gates ────────────────────────────────────────────────────────────

  if (AUTH_REQUIRED && isAuthBootstrapping) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-(--oc-bg)">
        <p className="text-sm text-(--oc-muted)">Checking session…</p>
      </main>
    )
  }

  if (AUTH_REQUIRED && !authSession) {
    return <LoginView isSubmitting={isSigningIn} error={authError} onLogin={handleLogin} />
  }

  const requiresCampaignScope = activeView !== 'dashboard' && activeView !== 'campaigns' && activeView !== 'uploads' && activeView !== 'settings' && activeView !== 'queue-history'

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <AppShell
        className="min-h-0 flex-1"
        activeView={activeView}
        setActiveView={navigateToView}
        activeCampaignName={activeCampaignName}
        campaigns={campaigns}
        selectedCampaignId={selectedCampaignId}
        onSelectCampaign={setSelectedCampaignId}
        stats={null}
        onOpenPromptLibrary={() => {}}
        authEnabled={AUTH_REQUIRED}
        userDisplayName={authSession?.displayName ?? null}
        onLogout={AUTH_REQUIRED ? handleLogout : undefined}
      >
        {requiresCampaignScope && !selectedCampaignId ? (
          <div className="space-y-3 rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-6">
            <p className="text-sm text-(--oc-muted)">Select a campaign from Campaigns to view scoped pipeline data.</p>
            <button type="button" className="rounded-xl bg-(--oc-accent) px-3 py-2 text-xs font-bold text-white" onClick={() => navigateToView('campaigns')}>
              Go to Campaigns
            </button>
          </div>
        ) : null}

        {activeView === 'dashboard' && (
          <DashboardView
            servicesHealth={servicesHealth}
            isLoadingHealth={isLoadingHealth}
            hasSelectedCampaign={Boolean(selectedCampaignId)}
            activeCampaignName={activeCampaignName}
            onNavigate={(view) => navigateToView(view)}
            onNavigateToUploads={() => navigateToView('uploads')}
            onOpenCampaigns={() => navigateToView('campaigns')}
            onOpenSettings={() => navigateToView('settings')}
          />
        )}

        {activeView === 'campaigns' && (
          <CampaignsView
            campaigns={campaigns}
            selectedCampaignId={selectedCampaignId}
            onSelectCampaign={(id) => setCampaignFromUser(id)}
            onNavigateToDashboard={() => navigateToView('dashboard')}
            onCreate={(name, description) => void onCreateCampaign(name, description)}
            onEdit={() => Promise.resolve()}
            onDelete={(campaignId) => void onDeleteCampaign(campaignId)}
          />
        )}

        {activeView === 'uploads' && (
          <ImportView
            campaigns={campaigns}
            selectedCampaignId={selectedCampaignId}
            uploads={uploads}
            onUpload={onUploadFromView}
            onNavigateToPipeline={() => navigateToView('s1-scraping')}
          />
        )}

        {activeView === 'settings' && <SettingsView />}

        {activeView === 'queue-history' && (
          <QueueHistoryView campaignId={selectedCampaignId} />
        )}

        {selectedCampaignId && activeView === 's1-scraping' && (
          <ScrapingView
            campaignId={selectedCampaignId}
            sseUrl={`/v1/campaigns/${selectedCampaignId}/events/stream`}
          />
        )}

        {selectedCampaignId && activeView === 'full-pipeline'   && <ComingSoon label="Full Pipeline" />}
        {selectedCampaignId && activeView === 's2-ai'           && <AIReviewView stats={null} />}
        {selectedCampaignId && activeView === 's3-contacts'     && <ContactsView stats={null} />}
        {selectedCampaignId && activeView === 's4-reveal'       && <ComingSoon label="S4 · Reveal" />}
        {selectedCampaignId && activeView === 's5-validation'   && <ValidationView stats={null} />}
        {selectedCampaignId && activeView === 'operations'      && <ComingSoon label="Operations Log" />}

      </AppShell>

      <Toast error={error} notice={notice} noticeAction={noticeAction} />
      {busyMessage !== null && <GlobalLoadingOverlay message={busyMessage} />}
    </>
  )
}

export default App
