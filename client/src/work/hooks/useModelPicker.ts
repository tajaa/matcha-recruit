import { useCallback, useState } from 'react'
import { DEFAULT_MODEL, LEGACY_MODEL_IDS, modelOptionsFor } from '../components/panels/constants'
import { useEntitlements } from './useEntitlements'

const STORAGE_KEY = 'mw-model'

function readStoredModel(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) || DEFAULT_MODEL
    return LEGACY_MODEL_IDS[stored] ?? stored
  } catch {
    return DEFAULT_MODEL
  }
}

/** The chat model picker shared by thread and project chat: the options this
 *  person may pick, the remembered pick, and its setter. A remembered pick
 *  that is no longer offered (Claude switched off, plan downgraded) reads as
 *  the default, so the request never carries a model the menu doesn't show. */
export function useModelPicker() {
  const { can, claudeModels } = useEntitlements()
  const [stored, setStored] = useState(readStoredModel)
  const modelOptions = modelOptionsFor({ claude: claudeModels, pro: can('ai_model_pro') })
  const selectedModel = modelOptions.some((option) => option.id === stored) ? stored : DEFAULT_MODEL
  const setSelectedModel = useCallback((model: string) => {
    setStored(model)
    try {
      localStorage.setItem(STORAGE_KEY, model)
    } catch { /* storage unavailable: the pick lasts for this page only */ }
  }, [])
  return { modelOptions, selectedModel, setSelectedModel }
}
