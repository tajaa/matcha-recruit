import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cappeApi } from '../../api'
import type { CappeThemePreset } from '../../data/cappeThemes'
import type { CappePagePreset } from '../../data/cappePagePresets'
import type { CappePage, CappeSite } from '../../types'
import { bizFromMeta, bizToMeta, type BizMeta } from './bizMeta'

export function useCappeSiteEditor() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [site, setSite] = useState<CappeSite | null>(null)
  const [pages, setPages] = useState<CappePage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [subdomain, setSubdomain] = useState('')
  const [logo, setLogo] = useState('')
  const [timezone, setTimezone] = useState('UTC')
  const [biz, setBiz] = useState<BizMeta>(bizFromMeta(undefined))
  const [saving, setSaving] = useState(false)
  const [themeBusy, setThemeBusy] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [setupRefresh, setSetupRefresh] = useState(0)
  const [newPageTitle, setNewPageTitle] = useState('')
  const [addingPage, setAddingPage] = useState(false)

  useEffect(() => {
    if (!siteId) return
    Promise.all([
      cappeApi.get<CappeSite>(`/sites/${siteId}`),
      cappeApi.get<CappePage[]>(`/sites/${siteId}/pages`),
    ])
      .then(([s, p]) => {
        setSite(s)
        setPages(p)
        setName(s.name)
        setSubdomain(s.subdomain || s.slug)
        setLogo((s.meta_config?.logo_url as string) || '')
        setTimezone(s.timezone || 'UTC')
        setBiz(bizFromMeta(s.meta_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load site'))
      .finally(() => setLoading(false))
  }, [siteId])

  async function save() {
    if (!siteId) return
    setSaving(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        name,
        timezone,
        meta_config: {
          ...(site?.meta_config || {}),
          logo_url: logo.trim() || null,
          ...bizToMeta(biz),
        },
      }
      // Only send subdomain when it actually changed (avoids a needless slug
      // churn + uniqueness check on every save).
      if (subdomain && subdomain !== (site?.subdomain || site?.slug)) body.subdomain = subdomain
      const updated = await cappeApi.put<CappeSite>(`/sites/${siteId}`, body)
      setSite(updated)
      setSubdomain(updated.subdomain || updated.slug)
      setSetupRefresh((n) => n + 1) // re-check the launch checklist after edits
      setNotice('Saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function applyTheme(preset: CappeThemePreset) {
    if (!siteId) return
    setThemeBusy(preset.id)
    setError(null)
    setNotice(null)
    try {
      const updated = await cappeApi.put<CappeSite>(`/sites/${siteId}`, {
        theme_config: { ...preset.config, preset: preset.id },
      })
      setSite(updated)
      setNotice(`Theme "${preset.name}" applied.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply theme')
    } finally {
      setThemeBusy(null)
    }
  }

  async function publish() {
    if (!siteId) return
    setPublishing(true)
    setError(null)
    try {
      const updated = await cappeApi.post<CappeSite>(`/sites/${siteId}/publish`)
      setSite(updated)
      setPages((prev) => prev.map((p) => (p.status === 'draft' ? { ...p, status: 'published' } : p)))
      setNotice('Site published.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to publish')
    } finally {
      setPublishing(false)
    }
  }

  async function createPage(title: string, content?: Record<string, unknown>) {
    if (!siteId || !title.trim()) return
    setAddingPage(true)
    try {
      const body: Record<string, unknown> = { title: title.trim() }
      if (content) body.content = content
      const page = await cappeApi.post<CappePage>(`/sites/${siteId}/pages`, body)
      setPages((prev) => [...prev, page])
      setNewPageTitle('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add page')
    } finally {
      setAddingPage(false)
    }
  }

  async function addPage(e: React.FormEvent) {
    e.preventDefault()
    await createPage(newPageTitle)
  }

  function addPreset(p: CappePagePreset) {
    if (addingPage) return
    createPage(p.title, { blocks: p.blocks })
  }

  async function deletePage(pageId: string) {
    if (!siteId) return
    try {
      await cappeApi.delete(`/sites/${siteId}/pages/${pageId}`)
      setPages((prev) => prev.filter((p) => p.id !== pageId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete page')
    }
  }

  async function deleteSite() {
    if (!siteId || !confirm('Delete this site and all its pages? This cannot be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}`)
      navigate('/cappe/sites')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete site')
    }
  }

  return {
    siteId, site, pages, loading, error, notice,
    name, setName, subdomain, setSubdomain, logo, setLogo, timezone, setTimezone,
    biz, setBiz, saving, themeBusy, publishing, setupRefresh,
    newPageTitle, setNewPageTitle, addingPage,
    save, applyTheme, publish, addPage, addPreset, deletePage, deleteSite,
  }
}
