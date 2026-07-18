import { IRAnonymousReportingPanel } from '../../../components/ir/IRAnonymousReportingPanel'

export default function IRAnonymousReporting() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-light text-zinc-50 tracking-tight">Magic Links</h1>
        <p className="mt-1.5 text-sm text-zinc-500 font-serif italic" style={{ fontFamily: 'Fraunces, Georgia, serif' }}>
          Anonymous, single-use company link and reusable per-location intake links.
        </p>
      </div>

      <IRAnonymousReportingPanel />
    </div>
  )
}
