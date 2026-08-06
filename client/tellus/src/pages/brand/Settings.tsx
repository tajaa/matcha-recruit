import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, ErrorText, Input, Spinner } from '../../components/ui'
import type { Brand, BrandPrompt } from '../../api/types'

export default function BrandSettings() {
  const [brand, setBrand] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [logo, setLogo] = useState('')
  const [rewardMode, setRewardMode] = useState<'auto' | 'manual'>('auto')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const [questions, setQuestions] = useState<string[]>([])
  const [qBusy, setQBusy] = useState(false)
  const [qMsg, setQMsg] = useState('')
  const [qErr, setQErr] = useState('')

  useEffect(() => {
    tellusApi.get<Brand>('/brand').then((b) => {
      setBrand(b); setName(b.name); setLogo(b.logo_url ?? ''); setRewardMode(b.reward_mode)
    })
    tellusApi.get<BrandPrompt[]>('/brand/prompts').then((ps) => setQuestions(ps.map((p) => p.prompt))).catch(() => {})
  }, [])

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
      const b = await tellusApi.patch<Brand>('/brand', { name, logo_url: logo || null, reward_mode: rewardMode })
      setBrand(b); setMsg('Saved.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Save failed') } finally { setBusy(false) }
  }

  if (!brand) return <Spinner />

  return (
    <div className="max-w-lg space-y-5">
      <h1 className="text-lg font-bold">Brand settings</h1>
      <Card className="space-y-4">
        <Input label="Brand name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input label="Logo URL" value={logo} onChange={(e) => setLogo(e.target.value)} placeholder="https://…" />
        {logo && <img src={logo} alt="" className="h-16 w-16 rounded-xl object-cover" />}
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
