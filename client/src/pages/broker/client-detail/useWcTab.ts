import { useState, useEffect, useRef, type FormEvent, type ChangeEvent } from 'react'
import {
  fetchWcClientDetail, recordWcMod, deleteWcMod, parseWcModWorksheet,
  fetchWcClassCodes, fetchWcClassExposures, recordWcClassExposure, deleteWcClassExposure,
  autoMapClassExposures, type ClassAutoMap,
} from '../../../api/broker/broker'
import type {
  WcClientDetailResponse, WcClassCode, WcClassExposure,
} from '../../../types/broker'

export function useWcTab(companyId: string) {
  const [detail, setDetail] = useState<WcClientDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
  const [source, setSource] = useState<'manual' | 'worksheet'>('manual')
  const [saving, setSaving] = useState(false)
  const [formErr, setFormErr] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)
  const [parseMsg, setParseMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const onWorksheet = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''  // allow re-selecting the same file
    if (!file) return
    setParsing(true); setParseMsg(null)
    try {
      const res = await parseWcModWorksheet(companyId, file)
      if (!res.available || res.fields.experience_mod == null) {
        setParseMsg('Could not read a mod from that PDF — enter it manually below.'); setShowForm(true); return
      }
      const f = res.fields
      const mod = res.fields.experience_mod
      setForm({
        policy_period_start: f.policy_period_start ?? '', experience_mod: String(mod),
        carrier: f.carrier ?? '', annual_premium: '', note: 'Auto-extracted from experience-rating worksheet',
      })
      setSource('worksheet'); setShowForm(true)
      setParseMsg(`Extracted mod ${mod.toFixed(2)} from the worksheet — review and save.`)
    } catch {
      setParseMsg('Worksheet parse failed — enter the mod manually below.'); setShowForm(true)
    } finally { setParsing(false) }
  }

  const load = () => {
    setLoading(true)
    setError(false)
    fetchWcClientDetail(companyId)
      .then(setDetail)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }
  useEffect(load, [companyId])

  const submitMod = async (e: FormEvent) => {
    e.preventDefault()
    const mod = parseFloat(form.experience_mod)
    if (!form.policy_period_start || !mod || mod <= 0) {
      setFormErr('Enter a policy start date and a positive experience mod.')
      return
    }
    setSaving(true)
    setFormErr(null)
    try {
      await recordWcMod(companyId, {
        policy_period_start: form.policy_period_start,
        experience_mod: mod,
        carrier: form.carrier || undefined,
        annual_premium: form.annual_premium ? parseFloat(form.annual_premium) : undefined,
        note: form.note || undefined,
        source,
      })
      setForm({ policy_period_start: '', experience_mod: '', carrier: '', annual_premium: '', note: '' })
      setSource('manual'); setParseMsg(null)
      setShowForm(false)
      load()
    } catch {
      setFormErr('Could not save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  const removeMod = async (id: string) => {
    try {
      await deleteWcMod(companyId, id)
      load()
    } catch { /* leave list as-is on failure */ }
  }

  return {
    detail, loading, error,
    showForm, setShowForm,
    form, setForm,
    setSource,
    saving, formErr,
    parsing, parseMsg, setParseMsg,
    fileRef,
    onWorksheet, submitMod, removeMod,
  }
}

export function useWcClassExposures(companyId: string) {
  const [exposures, setExposures] = useState<WcClassExposure[]>([])
  const [codes, setCodes] = useState<WcClassCode[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ class_code: '', state: '', payroll: '', headcount: '', note: '' })
  const [saving, setSaving] = useState(false)
  const [autoProps, setAutoProps] = useState<ClassAutoMap | null>(null)
  const [autoBusy, setAutoBusy] = useState(false)
  const [savingAll, setSavingAll] = useState(false)

  const load = () => { fetchWcClassExposures(companyId).then((r) => setExposures(r.exposures)).catch(() => {}) }
  useEffect(() => {
    load()
    fetchWcClassCodes().then((r) => setCodes(r.class_codes)).catch(() => {})
  }, [companyId])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.class_code) return
    setSaving(true)
    try {
      const r = await recordWcClassExposure(companyId, {
        class_code: form.class_code, state: form.state || undefined,
        payroll: form.payroll ? parseFloat(form.payroll) : undefined,
        headcount: form.headcount ? parseInt(form.headcount, 10) : undefined,
        note: form.note || undefined,
      })
      setExposures(r.exposures)
      setForm({ class_code: '', state: '', payroll: '', headcount: '', note: '' }); setShowForm(false)
    } catch { /* leave as-is */ } finally { setSaving(false) }
  }
  const remove = async (id: string) => { try { await deleteWcClassExposure(companyId, id); load() } catch { /* noop */ } }

  const runAutoMap = async () => {
    setAutoBusy(true); setAutoProps(null)
    try { setAutoProps(await autoMapClassExposures(companyId)) } catch { /* noop */ } finally { setAutoBusy(false) }
  }
  const saveAll = async () => {
    if (!autoProps?.proposed.length) return
    setSavingAll(true)
    try {
      for (const p of autoProps.proposed) {
        await recordWcClassExposure(companyId, { class_code: p.class_code, state: p.state, payroll: p.payroll, headcount: p.headcount })
      }
      setAutoProps(null); load()
    } catch { /* leave */ } finally { setSavingAll(false) }
  }

  const totalPremium = exposures.reduce((s, e) => s + (e.est_manual_premium ?? 0), 0)

  return {
    exposures, codes,
    showForm, setShowForm,
    form, setForm,
    saving,
    autoProps, autoBusy, savingAll,
    submit, remove, runAutoMap, saveAll,
    totalPremium,
  }
}
