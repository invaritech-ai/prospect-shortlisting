import { useCallback, useRef, useState } from 'react'
import type { PromptRead } from '../lib/types'
import { createPrompt, deletePrompt, listPrompts, updatePrompt } from '../lib/api'
import { parseApiError } from '../lib/utils'

const PROMPT_SELECTION_KEY = 'ps:selected-prompt-id'

export interface UsePromptManagementResult {
  prompts: PromptRead[]
  selectedPromptId: string
  selectedPrompt: PromptRead | null
  editingPromptId: string | null
  promptName: string
  promptText: string
  promptScrapeIntentText: string
  promptEnabled: boolean
  isPromptsLoading: boolean
  isPromptSaving: boolean
  isPromptDeleting: boolean
  promptError: string
  promptSheetOpen: boolean
  setPromptName: (v: string) => void
  setPromptText: (v: string) => void
  setPromptScrapeIntentText: (v: string) => void
  setPromptEnabled: (v: boolean) => void
  setSelectedPromptId: (v: string) => void
  loadPrompts: (preferredId?: string, preserveEditor?: boolean) => Promise<void>
  onSelectPrompt: (prompt: PromptRead) => void
  onNewPrompt: () => void
  onSavePromptAsNew: () => Promise<void>
  onUpdateCurrentPrompt: () => Promise<void>
  onTogglePromptEnabled: (prompt: PromptRead) => Promise<void>
  onDeletePrompt: (prompt: PromptRead) => Promise<void>
  onClonePrompt: (prompt: PromptRead) => Promise<void>
  openPromptSheet: () => void
  closePromptSheet: () => void
}

export function usePromptManagement(
  setError: (e: string) => void,
  setNotice: (n: string) => void,
): UsePromptManagementResult {
  const editingPromptIdRef = useRef<string | null>(null)
  const selectedPromptIdRef = useRef('')

  const [prompts, setPrompts] = useState<PromptRead[]>([])
  const [selectedPromptIdState, setSelectedPromptIdState] = useState('')
  const [editingPromptIdState, setEditingPromptIdState] = useState<string | null>(null)
  const [promptName, setPromptName] = useState('')
  const [promptText, setPromptText] = useState('')
  const [promptScrapeIntentText, setPromptScrapeIntentText] = useState('')
  const [promptEnabled, setPromptEnabled] = useState(true)
  const [isPromptsLoading, setIsPromptsLoading] = useState(false)
  const [isPromptSaving, setIsPromptSaving] = useState(false)
  const [isPromptDeleting, setIsPromptDeleting] = useState(false)
  const [promptError, setPromptError] = useState('')
  const [promptSheetOpen, setPromptSheetOpen] = useState(false)

  const setSelectedPromptId = useCallback((v: string) => {
    selectedPromptIdRef.current = v
    setSelectedPromptIdState(v)
  }, [])

  const setEditingPromptId = useCallback((v: string | null) => {
    editingPromptIdRef.current = v
    setEditingPromptIdState(v)
  }, [])

  const loadPrompts = useCallback(
    async (preferredPromptId?: string, preserveEditor = false) => {
      setIsPromptsLoading(true)
      try {
        const rows = await listPrompts()
        setPrompts(rows)
        setPromptError('')
        const stored = window.localStorage.getItem(PROMPT_SELECTION_KEY) ?? ''
        const preferredId =
          (preferredPromptId && rows.find((p) => p.id === preferredPromptId && p.enabled)?.id) ||
          (selectedPromptIdRef.current && rows.find((p) => p.id === selectedPromptIdRef.current && p.enabled)?.id) ||
          rows.find((p) => p.id === stored && p.enabled)?.id ||
          rows.find((p) => p.enabled)?.id ||
          rows[0]?.id ||
          ''
        setSelectedPromptId(preferredId)
        if (preferredId) window.localStorage.setItem(PROMPT_SELECTION_KEY, preferredId)
        else window.localStorage.removeItem(PROMPT_SELECTION_KEY)

        if (!preserveEditor) {
          const forEditor =
            rows.find(
              (p) => p.id === (preferredPromptId || editingPromptIdRef.current || preferredId),
            ) ??
            rows[0] ??
            null
          if (forEditor) {
            setEditingPromptId(forEditor.id)
            setPromptName(forEditor.name)
            setPromptText(forEditor.prompt_text)
            setPromptScrapeIntentText(forEditor.scrape_pages_intent_text ?? '')
            setPromptEnabled(forEditor.enabled)
          } else {
            setEditingPromptId(null)
            setPromptName('')
            setPromptText('')
            setPromptScrapeIntentText('')
            setPromptEnabled(true)
          }
        }
      } catch (err) {
        setPromptError(parseApiError(err))
      } finally {
        setIsPromptsLoading(false)
      }
    },
    [setSelectedPromptId, setEditingPromptId],
  )

  const onSelectPrompt = useCallback(
    (prompt: PromptRead) => {
      setSelectedPromptId(prompt.id)
      setEditingPromptId(prompt.id)
      setPromptName(prompt.name)
      setPromptText(prompt.prompt_text)
      setPromptScrapeIntentText(prompt.scrape_pages_intent_text ?? '')
      setPromptEnabled(prompt.enabled)
    },
    [setSelectedPromptId, setEditingPromptId],
  )

  const onNewPrompt = useCallback(() => {
    setEditingPromptId(null)
    setPromptName('')
    setPromptText('')
    setPromptScrapeIntentText('')
    setPromptEnabled(true)
    setPromptError('')
  }, [setEditingPromptId])

  const onSavePromptAsNew = useCallback(async () => {
    if (!promptName.trim() || !promptText.trim()) {
      setPromptError('Name and prompt text are required.')
      return
    }
    setIsPromptSaving(true)
    try {
      const created = await createPrompt({
        name: promptName.trim(),
        prompt_text: promptText.trim(),
        enabled: promptEnabled,
        scrape_pages_intent_text: promptScrapeIntentText.trim() || null,
      })
      await loadPrompts(created.id)
      setNotice(`Prompt "${created.name}" created.`)
      setError('')
    } catch (err) {
      setPromptError(parseApiError(err))
    } finally {
      setIsPromptSaving(false)
    }
  }, [promptName, promptText, promptEnabled, promptScrapeIntentText, loadPrompts, setError, setNotice])

  const onUpdateCurrentPrompt = useCallback(async () => {
    if (!editingPromptIdState) {
      setPromptError('Select an existing prompt to update.')
      return
    }
    if (!promptName.trim() || !promptText.trim()) {
      setPromptError('Name and prompt text are required.')
      return
    }
    setIsPromptSaving(true)
    try {
      const updated = await updatePrompt(editingPromptIdState, {
        name: promptName.trim(),
        prompt_text: promptText.trim(),
        enabled: promptEnabled,
        scrape_pages_intent_text: promptScrapeIntentText.trim() || null,
      })
      await loadPrompts(updated.id)
      setNotice(`Prompt "${updated.name}" updated.`)
      setError('')
    } catch (err) {
      setPromptError(parseApiError(err))
    } finally {
      setIsPromptSaving(false)
    }
  }, [editingPromptIdState, promptName, promptText, promptEnabled, promptScrapeIntentText, loadPrompts, setError, setNotice])

  const onTogglePromptEnabled = useCallback(
    async (prompt: PromptRead) => {
      setIsPromptSaving(true)
      try {
        const updated = await updatePrompt(prompt.id, { enabled: !prompt.enabled })
        await loadPrompts(updated.id, editingPromptIdState !== updated.id)
        if (editingPromptIdState === updated.id) setPromptEnabled(updated.enabled)
      } catch (err) {
        setPromptError(parseApiError(err))
      } finally {
        setIsPromptSaving(false)
      }
    },
    [editingPromptIdState, loadPrompts],
  )

  const onDeletePrompt = useCallback(
    async (prompt: PromptRead) => {
      setIsPromptDeleting(true)
      setPromptError('')
      try {
        await deletePrompt(prompt.id)
        if (selectedPromptIdRef.current === prompt.id) {
          selectedPromptIdRef.current = ''
          setSelectedPromptIdState('')
          window.localStorage.removeItem(PROMPT_SELECTION_KEY)
        }
        if (editingPromptIdRef.current === prompt.id) {
          editingPromptIdRef.current = null
          setEditingPromptIdState(null)
          setPromptName('')
          setPromptText('')
          setPromptScrapeIntentText('')
          setPromptEnabled(true)
        }
        await loadPrompts()
        setNotice(`Prompt "${prompt.name}" deleted.`)
        setError('')
      } catch (err) {
        setPromptError(parseApiError(err))
      } finally {
        setIsPromptDeleting(false)
      }
    },
    [loadPrompts, setError, setNotice],
  )

  const onClonePrompt = useCallback(
    async (prompt: PromptRead) => {
      setIsPromptSaving(true)
      setPromptError('')
      try {
        const created = await createPrompt({
          name: `Copy of ${prompt.name}`,
          prompt_text: prompt.prompt_text,
          scrape_pages_intent_text: prompt.scrape_pages_intent_text ?? null,
          enabled: false,
        })
        await loadPrompts(created.id)
        setNotice(`Cloned as "${created.name}".`)
        setError('')
      } catch (err) {
        setPromptError(parseApiError(err))
      } finally {
        setIsPromptSaving(false)
      }
    },
    [loadPrompts, setError, setNotice],
  )

  const openPromptSheet = useCallback(() => {
    setPromptSheetOpen(true)
    if (prompts.length === 0) void loadPrompts()
  }, [prompts.length, loadPrompts])

  const closePromptSheet = useCallback(() => {
    setPromptSheetOpen(false)
    setPromptError('')
  }, [])

  const selectedPrompt = prompts.find((p) => p.id === selectedPromptIdState) ?? null

  return {
    prompts,
    selectedPromptId: selectedPromptIdState,
    selectedPrompt,
    editingPromptId: editingPromptIdState,
    promptName,
    promptText,
    promptScrapeIntentText,
    promptEnabled,
    isPromptsLoading,
    isPromptSaving,
    isPromptDeleting,
    promptError,
    promptSheetOpen,
    setPromptName,
    setPromptText,
    setPromptScrapeIntentText,
    setPromptEnabled,
    setSelectedPromptId,
    loadPrompts,
    onSelectPrompt,
    onNewPrompt,
    onSavePromptAsNew,
    onUpdateCurrentPrompt,
    onTogglePromptEnabled,
    onDeletePrompt,
    onClonePrompt,
    openPromptSheet,
    closePromptSheet,
  }
}
