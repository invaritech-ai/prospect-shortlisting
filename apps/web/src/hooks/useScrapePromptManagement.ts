import { useCallback, useRef, useState } from 'react'
import type { ScrapePageKind, ScrapePromptRead } from '../lib/types'
import {
  ApiError,
  activateScrapePrompt,
  createScrapePrompt,
  deleteScrapePrompt,
  listScrapePrompts,
  updateScrapePrompt,
} from '../lib/api'
import { parseApiError } from '../lib/utils'

const SCRAPE_PROMPT_SELECTION_KEY = 'ps:selected-scrape-prompt-id'
const COMPAT_DEFAULT_SCRAPE_PROMPT_ID = 'compat-default-scrape-prompt'

function buildCompatDefaultScrapePrompt(): ScrapePromptRead {
  const now = new Date().toISOString()
  const pageKinds: ScrapePageKind[] = ['about', 'products', 'contact', 'team', 'leadership', 'services', 'pricing']
  const compiledPromptText = ['Find the best URL for each of these page types:', ...pageKinds.map((kind) => `- ${kind}`)].join('\n')
  return {
    id: COMPAT_DEFAULT_SCRAPE_PROMPT_ID,
    name: 'Default scrape prompt',
    enabled: true,
    is_system_default: true,
    is_active: true,
    intent_text: 'Find the best URL for each of these page types: about, products, contact, team, leadership, services, pricing.',
    compiled_prompt_text: compiledPromptText,
    scrape_rules_structured: {
      page_kinds: pageKinds,
      classifier_prompt_text: compiledPromptText,
    },
    created_at: now,
    updated_at: now,
  }
}

export interface UseScrapePromptManagementResult {
  scrapePrompts: ScrapePromptRead[]
  selectedScrapePromptId: string
  activeScrapePromptId: string
  activeScrapePrompt: ScrapePromptRead | null
  selectedScrapePrompt: ScrapePromptRead | null
  editingScrapePromptId: string | null
  scrapePromptName: string
  scrapePromptIntentText: string
  scrapePromptEnabled: boolean
  isScrapePromptsLoading: boolean
  isScrapePromptSaving: boolean
  isScrapePromptDeleting: boolean
  isScrapePromptApiUnavailable: boolean
  scrapePromptError: string
  scrapePromptSheetOpen: boolean
  setScrapePromptName: (v: string) => void
  setScrapePromptIntentText: (v: string) => void
  setScrapePromptEnabled: (v: boolean) => void
  setSelectedScrapePromptId: (v: string) => void
  loadScrapePrompts: (preferredId?: string, preserveEditor?: boolean) => Promise<void>
  onSelectScrapePrompt: (prompt: ScrapePromptRead) => void
  onNewScrapePrompt: () => void
  onSaveScrapePromptAsNew: () => Promise<void>
  onUpdateCurrentScrapePrompt: () => Promise<void>
  onToggleScrapePromptEnabled: (prompt: ScrapePromptRead) => Promise<void>
  onActivateScrapePrompt: (prompt: ScrapePromptRead) => Promise<void>
  onDeleteScrapePrompt: (prompt: ScrapePromptRead) => Promise<void>
  openScrapePromptSheet: () => void
  closeScrapePromptSheet: () => void
}

export function useScrapePromptManagement(
  setError: (e: string) => void,
  setNotice: (n: string) => void,
): UseScrapePromptManagementResult {
  const editingPromptIdRef = useRef<string | null>(null)
  const selectedPromptIdRef = useRef('')
  const scrapePromptApiUnavailableRef = useRef(false)
  const scrapePromptApiUnavailableNotifiedRef = useRef(false)

  const [scrapePrompts, setScrapePrompts] = useState<ScrapePromptRead[]>([])
  const [selectedScrapePromptIdState, setSelectedScrapePromptIdState] = useState('')
  const [activeScrapePromptId, setActiveScrapePromptId] = useState('')
  const [editingScrapePromptIdState, setEditingScrapePromptIdState] = useState<string | null>(null)
  const [scrapePromptName, setScrapePromptName] = useState('')
  const [scrapePromptIntentText, setScrapePromptIntentText] = useState('')
  const [scrapePromptEnabled, setScrapePromptEnabled] = useState(true)
  const [isScrapePromptsLoading, setIsScrapePromptsLoading] = useState(false)
  const [isScrapePromptSaving, setIsScrapePromptSaving] = useState(false)
  const [isScrapePromptDeleting, setIsScrapePromptDeleting] = useState(false)
  const [isScrapePromptApiUnavailable, setIsScrapePromptApiUnavailable] = useState(false)
  const [scrapePromptError, setScrapePromptError] = useState('')
  const [scrapePromptSheetOpen, setScrapePromptSheetOpen] = useState(false)

  const setSelectedScrapePromptId = useCallback((v: string) => {
    selectedPromptIdRef.current = v
    setSelectedScrapePromptIdState(v)
  }, [])

  const setEditingScrapePromptId = useCallback((v: string | null) => {
    editingPromptIdRef.current = v
    setEditingScrapePromptIdState(v)
  }, [])

  const applyPromptRows = useCallback(
    (rows: ScrapePromptRead[], preferredId?: string, preserveEditor = false) => {
      setScrapePrompts(rows)
      setScrapePromptError('')

      const active = rows.find((p) => p.is_active) ?? null
      const stored = window.localStorage.getItem(SCRAPE_PROMPT_SELECTION_KEY) ?? ''
      const preferredSelection =
        (preferredId && rows.find((p) => p.id === preferredId)?.id) ||
        (selectedPromptIdRef.current && rows.find((p) => p.id === selectedPromptIdRef.current)?.id) ||
        rows.find((p) => p.id === stored)?.id ||
        active?.id ||
        rows[0]?.id ||
        ''
      setSelectedScrapePromptId(preferredSelection)
      setActiveScrapePromptId(active?.id ?? '')

      if (preferredSelection) window.localStorage.setItem(SCRAPE_PROMPT_SELECTION_KEY, preferredSelection)
      else window.localStorage.removeItem(SCRAPE_PROMPT_SELECTION_KEY)

      const preservedEditor =
        preserveEditor && editingPromptIdRef.current
          ? rows.find((p) => p.id === editingPromptIdRef.current) ?? null
          : null
      const forEditor =
        preservedEditor ??
        rows.find((p) => p.id === (preferredId || preferredSelection)) ??
        rows[0] ??
        null

      if (forEditor) {
        setEditingScrapePromptId(forEditor.id)
        setScrapePromptName(forEditor.name)
        setScrapePromptIntentText(forEditor.intent_text ?? '')
        setScrapePromptEnabled(forEditor.enabled)
      } else {
        setEditingScrapePromptId(null)
        setScrapePromptName('')
        setScrapePromptIntentText('')
        setScrapePromptEnabled(true)
      }
    },
    [setEditingScrapePromptId, setSelectedScrapePromptId],
  )

  const loadScrapePrompts = useCallback(
    async (preferredId?: string, preserveEditor = false) => {
      if (scrapePromptApiUnavailableRef.current) {
        setIsScrapePromptApiUnavailable(true)
        applyPromptRows([buildCompatDefaultScrapePrompt()], preferredId, preserveEditor)
        return
      }
      setIsScrapePromptsLoading(true)
      try {
        const rows = await listScrapePrompts()
        applyPromptRows(rows, preferredId, preserveEditor)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          scrapePromptApiUnavailableRef.current = true
          setIsScrapePromptApiUnavailable(true)
          applyPromptRows([buildCompatDefaultScrapePrompt()], preferredId, preserveEditor)
          if (!scrapePromptApiUnavailableNotifiedRef.current) {
            scrapePromptApiUnavailableNotifiedRef.current = true
            setNotice('Scrape prompt API unavailable on this backend. Using built-in default scrape prompt.')
          }
          return
        }
        setScrapePromptError(parseApiError(err))
      } finally {
        setIsScrapePromptsLoading(false)
      }
    },
    [applyPromptRows, setNotice],
  )

  const ensureScrapePromptApiAvailable = useCallback((): boolean => {
    if (!scrapePromptApiUnavailableRef.current) return true
    setScrapePromptError('Scrape prompt editing is unavailable on this backend (missing /v1/scrape-prompts routes).')
    return false
  }, [])

  const onSelectScrapePrompt = useCallback(
    (prompt: ScrapePromptRead) => {
      setSelectedScrapePromptId(prompt.id)
      setEditingScrapePromptId(prompt.id)
      setScrapePromptName(prompt.name)
      setScrapePromptIntentText(prompt.intent_text ?? '')
      setScrapePromptEnabled(prompt.enabled)
    },
    [setEditingScrapePromptId, setSelectedScrapePromptId],
  )

  const onNewScrapePrompt = useCallback(() => {
    if (!ensureScrapePromptApiAvailable()) return
    setEditingScrapePromptId(null)
    setScrapePromptName('')
    setScrapePromptIntentText('')
    setScrapePromptEnabled(true)
    setScrapePromptError('')
  }, [ensureScrapePromptApiAvailable, setEditingScrapePromptId])

  const onSaveScrapePromptAsNew = useCallback(async () => {
    if (!ensureScrapePromptApiAvailable()) return
    if (!scrapePromptName.trim()) {
      setScrapePromptError('Name is required.')
      return
    }
    setIsScrapePromptSaving(true)
    try {
      const created = await createScrapePrompt({
        name: scrapePromptName.trim(),
        intent_text: scrapePromptIntentText.trim() || null,
        enabled: scrapePromptEnabled,
        set_active: false,
      })
      await loadScrapePrompts(created.id)
      setNotice(`Scrape prompt "${created.name}" created.`)
      setError('')
    } catch (err) {
      setScrapePromptError(parseApiError(err))
    } finally {
      setIsScrapePromptSaving(false)
    }
  }, [ensureScrapePromptApiAvailable, scrapePromptName, scrapePromptIntentText, scrapePromptEnabled, loadScrapePrompts, setError, setNotice])

  const onUpdateCurrentScrapePrompt = useCallback(async () => {
    if (!ensureScrapePromptApiAvailable()) return
    if (!editingScrapePromptIdState) {
      setScrapePromptError('Select an existing scrape prompt to update.')
      return
    }
    if (!scrapePromptName.trim()) {
      setScrapePromptError('Name is required.')
      return
    }
    setIsScrapePromptSaving(true)
    try {
      const updated = await updateScrapePrompt(editingScrapePromptIdState, {
        name: scrapePromptName.trim(),
        intent_text: scrapePromptIntentText.trim() || null,
        enabled: scrapePromptEnabled,
      })
      await loadScrapePrompts(updated.id)
      setNotice(`Scrape prompt "${updated.name}" updated.`)
      setError('')
    } catch (err) {
      setScrapePromptError(parseApiError(err))
    } finally {
      setIsScrapePromptSaving(false)
    }
  }, [
    editingScrapePromptIdState,
    scrapePromptName,
    scrapePromptIntentText,
    scrapePromptEnabled,
    ensureScrapePromptApiAvailable,
    loadScrapePrompts,
    setError,
    setNotice,
  ])

  const onToggleScrapePromptEnabled = useCallback(
    async (prompt: ScrapePromptRead) => {
      if (!ensureScrapePromptApiAvailable()) return
      setIsScrapePromptSaving(true)
      try {
        const updated = await updateScrapePrompt(prompt.id, { enabled: !prompt.enabled })
        await loadScrapePrompts(updated.id, editingScrapePromptIdState !== updated.id)
        if (editingScrapePromptIdState === updated.id) setScrapePromptEnabled(updated.enabled)
      } catch (err) {
        setScrapePromptError(parseApiError(err))
      } finally {
        setIsScrapePromptSaving(false)
      }
    },
    [editingScrapePromptIdState, ensureScrapePromptApiAvailable, loadScrapePrompts],
  )

  const onActivateScrapePrompt = useCallback(
    async (prompt: ScrapePromptRead) => {
      if (!ensureScrapePromptApiAvailable()) return
      if (!prompt.enabled) {
        setScrapePromptError('Enable this scrape prompt before activating it.')
        return
      }
      setIsScrapePromptSaving(true)
      try {
        const activated = await activateScrapePrompt(prompt.id)
        await loadScrapePrompts(activated.id, editingScrapePromptIdState !== activated.id)
        setNotice(`Scrape prompt "${activated.name}" is now active.`)
        setError('')
      } catch (err) {
        setScrapePromptError(parseApiError(err))
      } finally {
        setIsScrapePromptSaving(false)
      }
    },
    [editingScrapePromptIdState, ensureScrapePromptApiAvailable, loadScrapePrompts, setError, setNotice],
  )

  const onDeleteScrapePrompt = useCallback(
    async (prompt: ScrapePromptRead) => {
      if (!ensureScrapePromptApiAvailable()) return
      if (prompt.is_system_default) {
        setScrapePromptError('System default scrape prompt cannot be deleted.')
        return
      }
      setIsScrapePromptDeleting(true)
      setScrapePromptError('')
      try {
        await deleteScrapePrompt(prompt.id)
        if (selectedPromptIdRef.current === prompt.id) {
          selectedPromptIdRef.current = ''
          setSelectedScrapePromptIdState('')
          window.localStorage.removeItem(SCRAPE_PROMPT_SELECTION_KEY)
        }
        if (editingPromptIdRef.current === prompt.id) {
          editingPromptIdRef.current = null
          setEditingScrapePromptIdState(null)
          setScrapePromptName('')
          setScrapePromptIntentText('')
          setScrapePromptEnabled(true)
        }
        await loadScrapePrompts()
        setNotice(`Scrape prompt "${prompt.name}" deleted.`)
        setError('')
      } catch (err) {
        setScrapePromptError(parseApiError(err))
      } finally {
        setIsScrapePromptDeleting(false)
      }
    },
    [ensureScrapePromptApiAvailable, loadScrapePrompts, setError, setNotice],
  )

  const openScrapePromptSheet = useCallback(() => {
    setScrapePromptSheetOpen(true)
    if (scrapePrompts.length === 0) void loadScrapePrompts()
  }, [scrapePrompts.length, loadScrapePrompts])

  const closeScrapePromptSheet = useCallback(() => {
    setScrapePromptSheetOpen(false)
    setScrapePromptError('')
  }, [])

  const activeScrapePrompt = scrapePrompts.find((p) => p.id === activeScrapePromptId) ?? null
  const selectedScrapePrompt = scrapePrompts.find((p) => p.id === selectedScrapePromptIdState) ?? null

  return {
    scrapePrompts,
    selectedScrapePromptId: selectedScrapePromptIdState,
    activeScrapePromptId,
    activeScrapePrompt,
    selectedScrapePrompt,
    editingScrapePromptId: editingScrapePromptIdState,
    scrapePromptName,
    scrapePromptIntentText,
    scrapePromptEnabled,
    isScrapePromptsLoading,
    isScrapePromptSaving,
    isScrapePromptDeleting,
    isScrapePromptApiUnavailable,
    scrapePromptError,
    scrapePromptSheetOpen,
    setScrapePromptName,
    setScrapePromptIntentText,
    setScrapePromptEnabled,
    setSelectedScrapePromptId,
    loadScrapePrompts,
    onSelectScrapePrompt,
    onNewScrapePrompt,
    onSaveScrapePromptAsNew,
    onUpdateCurrentScrapePrompt,
    onToggleScrapePromptEnabled,
    onActivateScrapePrompt,
    onDeleteScrapePrompt,
    openScrapePromptSheet,
    closeScrapePromptSheet,
  }
}
