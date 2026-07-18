import { useEffect, useState, useRef } from 'react'
import { api } from '../../../api/client'
import { createBatchClientSetups } from '../../../api/broker/broker'
import type { BrokerBatchCreateResponse } from '../../../types/broker'
import type { ClientSetup, SetupForm, LocationEntry, CsvRow } from './types'
import { EMPTY_SETUP, EMPTY_LOCATION } from './constants'
import { parseCsv } from './csv'

export function useBrokerClients() {
  const [setups, setSetups] = useState<ClientSetup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [needsTerms, setNeedsTerms] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<SetupForm>(EMPTY_SETUP)
  const [saving, setSaving] = useState(false)
  const [addError, setAddError] = useState('')
  const [sendingInvite, setSendingInvite] = useState<string | null>(null)

  // CSV upload state
  const [showCsvUpload, setShowCsvUpload] = useState(false)
  const [csvRows, setCsvRows] = useState<CsvRow[]>([])
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvSubmitting, setCsvSubmitting] = useState(false)
  const [csvResult, setCsvResult] = useState<BrokerBatchCreateResponse | null>(null)
  const [csvError, setCsvError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  function fetchSetups() {
    setLoading(true)
    setNeedsTerms(false)
    api.get<{ setups: ClientSetup[] }>('/brokers/client-setups')
      .then((res) => setSetups(res.setups))
      .catch((err) => {
        const msg = err instanceof Error ? err.message : ''
        if (msg.toLowerCase().includes('terms')) {
          setNeedsTerms(true)
        } else {
          setError('Unable to load client setups')
        }
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchSetups() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setAddError('')
    setSaving(true)
    try {
      await api.post('/brokers/client-setups', {
        company_name: form.company_name.trim(),
        contact_name: form.contact_name.trim() || undefined,
        contact_email: form.contact_email.trim() || undefined,
        contact_phone: form.contact_phone.trim() || undefined,
        industry: form.industry.trim() || undefined,
        company_size: form.company_size.trim() || undefined,
        headcount: parseInt(form.headcount, 10) || undefined,
        invite_immediately: form.invite_immediately,
        locations: form.locations.length > 0 ? form.locations.filter((l) => l.city || l.state) : undefined,
        notes: form.notes.trim() || undefined,
        onboarding_template: form.specialties.trim() ? { specialties: form.specialties.trim() } : undefined,
      })
      setShowAdd(false)
      setForm(EMPTY_SETUP)
      fetchSetups()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to create client setup')
    } finally {
      setSaving(false)
    }
  }

  async function sendInvite(setupId: string) {
    setSendingInvite(setupId)
    try {
      await api.post(`/brokers/client-setups/${setupId}/send-invite`, { expires_days: 14 })
      fetchSetups()
    } catch {}
    setSendingInvite(null)
  }

  // Location helpers
  function addLocation() {
    setForm({ ...form, locations: [...form.locations, { ...EMPTY_LOCATION }] })
  }

  function removeLocation(idx: number) {
    setForm({ ...form, locations: form.locations.filter((_, i) => i !== idx) })
  }

  function updateLocation(idx: number, field: keyof LocationEntry, value: string) {
    const locs = [...form.locations]
    locs[idx] = { ...locs[idx], [field]: value }
    setForm({ ...form, locations: locs })
  }

  // CSV handlers
  function handleCsvFile(file: File) {
    setCsvFile(file)
    setCsvResult(null)
    setCsvError('')
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      const rows = parseCsv(text)
      setCsvRows(rows)
    }
    reader.readAsText(file)
  }

  function handleCsvDrop(e: React.DragEvent) {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.name.endsWith('.csv')) handleCsvFile(file)
  }

  async function submitCsvBatch() {
    setCsvSubmitting(true)
    setCsvError('')
    try {
      const clients = csvRows.map((r) => ({
        company_name: r.company_name,
        contact_name: r.contact_name || undefined,
        contact_email: r.contact_email || undefined,
        contact_phone: r.contact_phone || undefined,
        industry: r.industry || undefined,
        company_size: r.company_size || undefined,
        headcount: parseInt(r.headcount, 10) || undefined,
        notes: r.notes || undefined,
      }))
      const result = await createBatchClientSetups(clients)
      setCsvResult(result)
      fetchSetups()
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : 'Batch upload failed')
    } finally {
      setCsvSubmitting(false)
    }
  }

  function closeCsvModal() {
    setShowCsvUpload(false)
    setCsvRows([])
    setCsvFile(null)
    setCsvResult(null)
    setCsvError('')
  }

  return {
    setups, loading, error, needsTerms,
    showAdd, setShowAdd, form, setForm, saving, addError, setAddError, sendingInvite,
    showCsvUpload, setShowCsvUpload, csvRows, csvFile, csvSubmitting, csvResult, csvError, fileInputRef,
    fetchSetups, handleCreate, sendInvite,
    addLocation, removeLocation, updateLocation,
    handleCsvFile, handleCsvDrop, submitCsvBatch, closeCsvModal,
  }
}
