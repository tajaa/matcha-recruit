import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, Plus, Save } from 'lucide-react'
import { ApiError } from '../../api/tellusClient'
import { loyaltyApi } from '../../api/loyalty'
import { Button, Card, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type { LoyaltyCounterMode, LoyaltyEventKey, LoyaltyProgram } from '../../api/types'

const EVENTS: LoyaltyEventKey[] = ['visit', 'purchase', 'review', 'board_reply', 'follow', 'social_post']

function defaultProgram(): LoyaltyProgram {
  return {
    brand_id: '', brand_name: '', brand_slug: '', name: 'Rewards', point_singular: 'point', point_plural: 'points', terms: '', status: 'draft', counter_mode: 'purchase',
    rules: EVENTS.map((event_key) => event_key === 'purchase'
      ? { event_key, award_type: 'per_dollar', fixed_points: null, points_per_dollar: 1, min_purchase_cents: 100, max_points_per_event: 1000, daily_cap: 1000, cooldown_seconds: null, is_active: true }
      : { event_key, award_type: 'fixed', fixed_points: event_key === 'review' ? 50 : 10, points_per_dollar: null, min_purchase_cents: null, max_points_per_event: null, daily_cap: null, cooldown_seconds: null, is_active: event_key !== 'visit' }),
    tiers: [{ tier_key: 'bronze', threshold_points: 0, benefits: '' }, { tier_key: 'silver', threshold_points: 500, benefits: '' }, { tier_key: 'gold', threshold_points: 1500, benefits: '' }],
    rewards: [],
  }
}

export default function LoyaltyBuilder() {
  const { brandId = '' } = useParams()
  const [program, setProgram] = useState<LoyaltyProgram | null>(null)
  const [title, setTitle] = useState('')
  const [cost, setCost] = useState('100')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    loyaltyApi.getBuilder(brandId).then(setProgram).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) setProgram(defaultProgram())
      else setError(e instanceof Error ? e.message : 'Could not load loyalty builder.')
    })
  }, [brandId])

  function changeRule(eventKey: LoyaltyEventKey, field: string, value: string | boolean) {
    setProgram((current) => current ? {
      ...current,
      rules: current.rules.map((rule) => rule.event_key === eventKey ? {
        ...rule,
        [field]: field === 'is_active' ? value : Number(value),
      } : rule),
    } : current)
  }

  function bodyFor(status: 'draft' | 'active' | 'paused') {
    if (!program) return null
    return {
      name: program.name,
      point_singular: program.point_singular,
      point_plural: program.point_plural,
      terms: program.terms || null,
      status,
      counter_mode: program.counter_mode,
      rules: program.rules,
      tiers: program.tiers,
    }
  }

  async function save(status: 'draft' | 'active' | 'paused') {
    const body = bodyFor(status)
    if (!body) return
    setBusy(true); setError(''); setMessage('')
    try { setProgram(await loyaltyApi.saveBuilder(brandId, body)); setMessage(status === 'active' ? 'Program published.' : 'Draft saved.') }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save program.') }
    finally { setBusy(false) }
  }

  async function addReward() {
    if (!title.trim()) { setError('Give the reward a title first.'); return }
    setBusy(true); setError(''); setMessage('')
    try {
      if (program?.brand_id === '') await loyaltyApi.saveBuilder(brandId, bodyFor('draft'))
      const reward = await loyaltyApi.createReward(brandId, { title: title.trim(), points_cost: Number(cost), is_active: true })
      setProgram((current) => current ? { ...current, brand_id: brandId, rewards: [...current.rewards, reward] } : current)
      setTitle(''); setMessage('Reward added.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not add reward.') }
    finally { setBusy(false) }
  }

  if (!program) return <Spinner />
  return (
    <div className="space-y-6">
      <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-tu-accent">Brand loyalty</p><h1 className="mt-2 text-2xl font-black">Build your program</h1><p className="mt-1 text-sm text-tu-dim">Set the rules customers see at the counter and in the app.</p></div>
      {message && <p className="rounded-lg bg-tu-good/10 p-3 text-sm text-tu-good">{message}</p>}<ErrorText>{error}</ErrorText>
      <Card className="space-y-4"><h2 className="font-bold">Identity</h2><Input label="Program name" value={program.name} onChange={(e) => setProgram({ ...program, name: e.target.value })} /><div className="grid gap-3 sm:grid-cols-2"><Input label="Point singular" value={program.point_singular} onChange={(e) => setProgram({ ...program, point_singular: e.target.value })} /><Input label="Point plural" value={program.point_plural} onChange={(e) => setProgram({ ...program, point_plural: e.target.value })} /></div><Textarea label="Terms" value={program.terms ?? ''} onChange={(e) => setProgram({ ...program, terms: e.target.value })} /></Card>
      <Card className="space-y-4"><div className="flex items-center justify-between"><h2 className="font-bold">Counter earning</h2><Select aria-label="Counter mode" value={program.counter_mode} onChange={(e) => { const mode = e.target.value as LoyaltyCounterMode; setProgram({ ...program, counter_mode: mode, rules: program.rules.map((rule) => rule.event_key === 'visit' || rule.event_key === 'purchase' ? { ...rule, is_active: rule.event_key === mode } : rule) }) }} options={[{ value: 'purchase', label: 'Purchase amount' }, { value: 'visit', label: 'Visit punch' }]} /></div>{program.rules.map((rule) => <div key={rule.event_key} className="grid gap-3 rounded-lg border border-tu-border p-3 sm:grid-cols-[1fr_130px_100px] sm:items-end"><div><p className="text-sm font-semibold">{rule.event_key.replace('_', ' ')}</p><p className="text-xs text-tu-faint">{rule.event_key === 'purchase' ? 'Points per whole dollar' : 'Fixed points per event'}</p></div><Input type="number" label={rule.event_key === 'purchase' ? 'Points/$' : 'Points'} value={rule.event_key === 'purchase' ? rule.points_per_dollar ?? '' : rule.fixed_points ?? ''} onChange={(e) => changeRule(rule.event_key, rule.event_key === 'purchase' ? 'points_per_dollar' : 'fixed_points', e.target.value)} /><label className="flex items-center gap-2 pb-2 text-xs text-tu-dim"><input type="checkbox" checked={rule.is_active} onChange={(e) => changeRule(rule.event_key, 'is_active', e.target.checked)} /> Active</label></div>)}</Card>
      <Card className="space-y-4"><h2 className="font-bold">Bronze, Silver, Gold</h2>{program.tiers.map((tier) => <div key={tier.tier_key} className="grid gap-3 sm:grid-cols-[100px_160px_1fr] sm:items-end"><p className="text-sm font-semibold capitalize">{tier.tier_key}</p><Input type="number" label="Lifetime points" value={tier.threshold_points} disabled={tier.tier_key === 'bronze'} onChange={(e) => setProgram({ ...program, tiers: program.tiers.map((item) => item.tier_key === tier.tier_key ? { ...item, threshold_points: Number(e.target.value) } : item) })} /><Input label="Benefits" value={tier.benefits ?? ''} onChange={(e) => setProgram({ ...program, tiers: program.tiers.map((item) => item.tier_key === tier.tier_key ? { ...item, benefits: e.target.value } : item) })} /></div>)}</Card>
      <Card className="space-y-4"><div className="flex items-center justify-between"><h2 className="font-bold">Rewards</h2><span className="text-xs text-tu-faint">{program.rewards.length} active</span></div>{program.rewards.map((reward) => <div key={reward.id} className="flex items-center justify-between border-b border-tu-border pb-3 text-sm"><span>{reward.title}</span><span className="font-semibold text-tu-accent">{reward.points_cost} points</span></div>)}<div className="grid gap-3 sm:grid-cols-[1fr_140px_auto] sm:items-end"><Input label="New reward" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Free coffee" /><Input label="Cost" type="number" value={cost} onChange={(e) => setCost(e.target.value)} /><Button onClick={() => void addReward()} loading={busy}><Plus className="h-4 w-4" /> Add</Button></div></Card>
      <div className="flex flex-wrap justify-end gap-2"><Button variant="soft" onClick={() => void save('draft')} loading={busy}><Save className="h-4 w-4" /> Save draft</Button><Button onClick={() => void save('active')} loading={busy}><Check className="h-4 w-4" /> Publish program</Button></div>
    </div>
  )
}
