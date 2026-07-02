import { useEffect, useState } from 'react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, ErrorText, Input, Spinner } from '../../components/ui'
import type { Brand } from '../../api/types'

export default function BrandSettings() {
  const [brand, setBrand] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [logo, setLogo] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    tellusApi.get<Brand>('/brand').then((b) => { setBrand(b); setName(b.name); setLogo(b.logo_url ?? '') })
  }, [])

  async function save() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const b = await tellusApi.patch<Brand>('/brand', { name, logo_url: logo || null })
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
    </div>
  )
}
