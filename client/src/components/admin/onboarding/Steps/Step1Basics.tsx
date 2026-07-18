import { useEffect, useMemo, useState } from 'react'

import {
  adminOnboarding,
  type BasicsPayload,
} from '../../../../api/admin/adminOnboarding'
import { ErrorBox, FieldLabel, PrimaryButton, type StepProps } from './_shared'

// ── Step 1: Basics ──────────────────────────────────────────────────────

export function Step1Basics({ session, onUpdated, onNext }: StepProps) {
  const [specialties, setSpecialties] = useState<Record<string, string[]>>({})
  const [businessName, setBusinessName] = useState(session.basics.business_name || '')
  const [industry, setIndustry] = useState(session.basics.industry || '')
  const [specialty, setSpecialty] = useState(session.basics.specialty || '')
  const [description, setDescription] = useState(session.basics.description || '')
  const [ownerEmail, setOwnerEmail] = useState(session.basics.owner_email || '')
  const [ownerName, setOwnerName] = useState(session.basics.owner_name || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void adminOnboarding.specialties().then(setSpecialties).catch(() => undefined)
  }, [])

  const industryOptions = useMemo(() => Object.keys(specialties).sort(), [specialties])
  const specialtyOptions = specialties[industry] || []
  const valid = businessName.trim() && industry && ownerEmail.includes('@')

  async function save() {
    if (!valid || busy) return
    setBusy(true)
    setError(null)
    try {
      const payload: BasicsPayload = {
        business_name: businessName.trim(),
        industry,
        specialty: specialty || null,
        description: description.trim() || null,
        owner_email: ownerEmail.trim(),
        owner_name: ownerName.trim() || null,
      }
      const updated = await adminOnboarding.patchSession(session.id, {
        basics: payload,
        step: 'size',
      })
      onUpdated(updated)
      onNext()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h2 className="text-base font-medium text-zinc-100 mb-1">Business basics</h2>
      <p className="text-sm text-zinc-400 mb-6">
        Name, industry, sub-specialty, and the owner email we'll invite at the end.
      </p>
      <ErrorBox message={error} />

      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <FieldLabel>Business name</FieldLabel>
          <input
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            placeholder="Acme Diner"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Industry</FieldLabel>
          <select
            value={industry}
            onChange={(e) => { setIndustry(e.target.value); setSpecialty('') }}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          >
            <option value="">— pick —</option>
            {industryOptions.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel>Specialty</FieldLabel>
          <select
            value={specialty}
            onChange={(e) => setSpecialty(e.target.value)}
            disabled={specialtyOptions.length === 0}
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 disabled:opacity-50"
          >
            <option value="">{specialtyOptions.length ? '— optional —' : '— none —'}</option>
            {specialtyOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel>Owner email</FieldLabel>
          <input
            type="email"
            value={ownerEmail}
            onChange={(e) => setOwnerEmail(e.target.value)}
            placeholder="owner@example.com"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div>
          <FieldLabel>Owner name</FieldLabel>
          <input
            value={ownerName}
            onChange={(e) => setOwnerName(e.target.value)}
            placeholder="Jane Owner"
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500"
          />
        </div>
        <div className="col-span-2">
          <FieldLabel>
            Company description
            <span className="ml-2 normal-case tracking-normal text-zinc-500">
              · the AI uses this to find non-obvious requirements
            </span>
          </FieldLabel>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={5}
            maxLength={2000}
            placeholder={
              'What does this company actually do? Who works here ' +
              '(grad students, contractors, minors)? Notable activities, ' +
              'facilities, services, hours, hazards? Be specific — examples: ' +
              '"BSL-2 lab handling human tissue samples; 8 UCSF grad students ' +
              'on rotation; late-night work; no minors" or "full-service ' +
              'restaurant with bar; tipped staff; live music Fri/Sat past ' +
              'midnight; outdoor patio with heaters". The more detail, the ' +
              'better the AI can surface compliance the HR admin might miss.'
            }
            className="w-full rounded-md bg-vsc-bg border border-vsc-border px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 resize-y"
          />
          <div className="text-[11px] text-zinc-500 mt-1">
            {description.length} / 2000
          </div>
        </div>
      </div>

      <div className="mt-6">
        <PrimaryButton busy={busy} disabled={!valid} onClick={() => void save()}>
          Save + Continue
        </PrimaryButton>
      </div>
    </div>
  )
}
