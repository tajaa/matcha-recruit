import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, ErrorText, Input, Spinner } from '../../components/ui'
import type { Brand, BrandPrompt } from '../../api/types'

const LOGO_MAX_BYTES = 2 * 1024 * 1024

export default function BrandSettings() {
  const [brand, setBrand] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [rewardMode, setRewardMode] = useState<'auto' | 'manual'>('auto')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [logoBusy, setLogoBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const [questions, setQuestions] = useState<string[]>([])
  const [qBusy, setQBusy] = useState(false)
  const [qMsg, setQMsg] = useState('')
  const [qErr, setQErr] = useState('')

  useEffect(() => {
    tellusApi.get<Brand>('/brand').then((b) => {
      setBrand(b); setName(b.name); setRewardMode(b.reward_mode)
    })
    tellusApi.get<BrandPrompt[]>('/brand/prompts').then((ps) => setQuestions(ps.map((p) => p.prompt))).catch(() => {})
  }, [])

  async function uploadLogo(f: File) {
    if (f.size > LOGO_MAX_BYTES) { setErr('Logo must be 2MB or smaller.'); return }
    setLogoBusy(true); setErr(''); setMsg('')
    try {
      const form = new FormData()
      form.append('file', f)
      const b = await tellusApi.upload<Brand>('/brand/logo', form)
      setBrand(b); setMsg('Logo updated.')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setLogoBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function removeLogo() {
    setLogoBusy(true); setErr(''); setMsg('')
    try {
      const b = await tellusApi.delete<Brand>('/brand/logo')
      setBrand(b); setMsg('Logo removed.')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Remove failed')
    } finally {
      setLogoBusy(false)
    }
  }

  function moveQuestion(i: number, dir: -1 | 1) {
    setQuestions((qs) => {
      const next = [...qs]
      const j = i + dir
      if (j < 0 || j >= next.length) return qs
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }

  async function saveQuestions() {
    setQBusy(true); setQErr(''); setQMsg('')
    try {
      const ps = await tellusApi.put<BrandPrompt[]>('/brand/prompts', {
        prompts: questions.filter((q) => q.trim()).map((q) => ({ prompt: q.trim() })),
      })
      setQuestions(ps.map((p) => p.prompt))
      setQMsg('Saved.')
    } catch (e) {
      setQErr(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setQBusy(false)
    }
  }

  async function save() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const b = await tellusApi.patch<Brand>('/brand', { name, reward_mode: rewardMode })
      setBrand(b); setMsg('Saved.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Save failed') } finally { setBusy(false) }
  }

  if (!brand) return <Spinner />

  return (
    <div className="max-w-lg space-y-5">
      <h1 className="text-lg font-bold">Brand settings</h1>
      <Card className="space-y-4">
        <Input label="Brand name" value={name} onChange={(e) => setName(e.target.value)} />
        <div>
          <p className="mb-1.5 text-sm font-medium text-tu-dim">Logo</p>
          <div className="flex items-center gap-3">
            {brand.logo_url ? (
              <img src={brand.logo_url} alt="" className="h-16 w-16 rounded-xl object-cover" />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-tu-panel2 text-xs text-tu-faint">No logo</div>
            )}
            <div>
              <input
                ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadLogo(f) }}
              />
              <Button variant="soft" size="sm" loading={logoBusy} onClick={() => fileRef.current?.click()}>
                Upload logo
              </Button>
              {brand.logo_url && (
                <Button variant="ghost" size="sm" loading={logoBusy} onClick={removeLogo} className="text-tu-bad">
                  Remove
                </Button>
              )}
              <p className="mt-1 text-xs text-tu-faint">PNG, JPEG, or WebP. Max 2MB.</p>
            </div>
          </div>
        </div>
        <Button onClick={save} loading={busy} variant="soft">Save</Button>
        {msg && <p className="text-sm text-tu-good">{msg}</p>}
        <ErrorText>{err}</ErrorText>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Reward approval</h2>
        <p className="text-xs text-tu-faint">How feedback earns points for your customers.</p>
        {([
          { value: 'auto', label: 'Automatic', desc: 'Useful feedback earns points immediately on submission.' },
          { value: 'manual', label: 'Manual review', desc: 'You approve or decline each submission before points are awarded.' },
        ] as const).map((opt) => (
          <label key={opt.value} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
            rewardMode === opt.value ? 'border-tu-accent bg-tu-accent/5' : 'border-tu-border'
          }`}>
            <input type="radio" name="reward_mode" className="mt-1 accent-tu-accent"
              checked={rewardMode === opt.value} onChange={() => setRewardMode(opt.value)} />
            <span>
              <span className="block text-sm font-semibold">{opt.label}</span>
              <span className="block text-xs text-tu-dim">{opt.desc}</span>
            </span>
          </label>
        ))}
        <Button onClick={save} loading={busy}>Save reward mode</Button>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Feedback questions</h2>
        <p className="text-xs text-tu-faint">Up to 5 custom questions shown on your intake form, in order.</p>
        {questions.map((q, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="flex-1">
              <Input
                value={q}
                onChange={(e) => setQuestions((qs) => qs.map((x, idx) => (idx === i ? e.target.value : x)))}
                placeholder="e.g. How was our service today?"
              />
            </div>
            <button type="button" onClick={() => moveQuestion(i, -1)} disabled={i === 0} className="text-tu-faint hover:text-tu-text disabled:opacity-30">
              <ArrowUp className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => moveQuestion(i, 1)} disabled={i === questions.length - 1} className="text-tu-faint hover:text-tu-text disabled:opacity-30">
              <ArrowDown className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setQuestions((qs) => qs.filter((_, idx) => idx !== i))} className="text-tu-faint hover:text-tu-bad">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
        <Button
          variant="soft" size="sm"
          disabled={questions.length >= 5}
          onClick={() => setQuestions((qs) => [...qs, ''])}
        >
          Add question
        </Button>
        <Button onClick={saveQuestions} loading={qBusy}>Save questions</Button>
        {qMsg && <p className="text-sm text-tu-good">{qMsg}</p>}
        <ErrorText>{qErr}</ErrorText>
      </Card>
    </div>
  )
}
