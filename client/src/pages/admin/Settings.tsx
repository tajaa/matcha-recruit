import { useState } from 'react'
import { Card } from '../../components/ui'
import { Button } from '../../components/ui'

const models = [
  { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', description: 'Fast, cost-effective' },
  { id: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite', description: 'Lightest, lowest cost' },
  { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', description: 'Balanced speed and quality' },
  { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', description: 'Highest quality, slower' },
]

export default function Settings() {
  const [activeModel, setActiveModel] = useState('gemini-2.5-flash')
  const [saved, setSaved] = useState(false)

  function handleSave() {
    // TODO: wire to /api/admin/settings
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">
        Settings
      </h1>
      <p className="mt-2 text-sm text-zinc-500">Platform-wide configuration.</p>

      <div className="mt-8 max-w-xl">
        <h2 className="text-sm font-medium text-zinc-300 mb-3">AI Model</h2>
        <div className="space-y-2">
          {models.map((m) => (
            <Card
              key={m.id}
              className={`flex items-center gap-4 p-4 cursor-pointer transition-colors ${
                activeModel === m.id
                  ? 'border-emerald-500 bg-emerald-950/20'
                  : 'hover:border-zinc-700'
              }`}
              onClick={() => { setActiveModel(m.id); setSaved(false) }}
            >
              <div
                className={`h-3 w-3 rounded-full border-2 ${
                  activeModel === m.id
                    ? 'border-emerald-500 bg-emerald-500'
                    : 'border-zinc-600'
                }`}
              />
              <div>
                <p className="text-sm font-medium text-zinc-100">{m.label}</p>
                <p className="text-xs text-zinc-500">{m.description}</p>
              </div>
            </Card>
          ))}
        </div>

        <div className="mt-6">
          <Button onClick={handleSave}>
            {saved ? 'Saved' : 'Save changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}
