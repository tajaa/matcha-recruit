import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import type { RecapEvent } from '../../types'
import './scene.css'

type Scene = { event: RecapEvent; seconds: number }
declare global {
  interface Window {
    recapTemplate: string
    renderRecapScene: (scene: Scene) => void
  }
}

export function Card({ scene }: { scene: Scene }) {
  const event = scene.event
  return <main>
    <header><span>Espresso</span><span>Task recap · Saved result</span></header>
    <div className="outcome">{event.outcome.replaceAll('_', ' ')}</div>
    <h1>{event.title}</h1>
    <dl>{event.facts.map((fact, n) => <div key={n}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl>
    <footer>Key steps from actual task records <span>{new Date(event.occurred_at).toLocaleString('en-US', { timeZone: 'UTC' })} UTC</span></footer>
  </main>
}

const root = createRoot(document.getElementById('root')!)
window.renderRecapScene = (scene) => { flushSync(() => root.render(<Card scene={scene} />)) }
window.recapTemplate = 'espresso-recap.v1'
