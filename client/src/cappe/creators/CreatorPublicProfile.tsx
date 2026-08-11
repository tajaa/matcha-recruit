import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { BadgeCheck, ExternalLink, Loader2 } from 'lucide-react'
import { fetchPublicCreator, getCappeToken } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { ui, badgeFor } from '../components/ui'
import { fmtCents, type PublicCreatorProfile } from '../types'
import SendOfferSheet from './SendOfferSheet'
import { creatorPaths } from './creatorPaths'

export default function CreatorPublicProfile() {
  const { handle } = useParams<{ handle: string }>()
  const navigate = useNavigate()
  const { account } = useCappeMe()
  const [profile, setProfile] = useState<PublicCreatorProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [showOffer, setShowOffer] = useState(false)

  useEffect(() => {
    if (!handle) return
    setLoading(true)
    setNotFound(false)
    fetchPublicCreator(handle)
      .then(setProfile)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [handle])

  if (loading) {
    return <div className={`${ui.page} flex items-center justify-center`}><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  }
  if (notFound || !profile) {
    return <div className={`${ui.page} flex items-center justify-center text-sm text-zinc-500`}>Creator not found.</div>
  }

  const canOffer = account?.account_type === 'business'
  const isLoggedOut = !getCappeToken()
  const isHiddenCta = account && !canOffer

  return (
    <div className={ui.page}>
      <div className="h-48 bg-zinc-800" style={profile.cover_url ? { backgroundImage: `url(${profile.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined} />
      <div className="mx-auto max-w-4xl px-6">
        <div className="-mt-12 flex items-end justify-between">
          <div className="flex items-end gap-4">
            <div className="h-24 w-24 overflow-hidden rounded-full ring-4 ring-zinc-950 bg-zinc-800">
              {profile.avatar_url && <img src={profile.avatar_url} alt={profile.display_name} className="h-full w-full object-cover" />}
            </div>
            <div className="pb-1">
              <div className="flex items-center gap-1.5">
                <h1 className="text-xl font-semibold text-zinc-50">{profile.display_name}</h1>
                {profile.reach_verified && <BadgeCheck className="h-5 w-5 text-emerald-400" />}
              </div>
              <p className="text-sm text-zinc-500">@{profile.handle}{profile.location ? ` · ${profile.location}` : ''}</p>
            </div>
          </div>
          {!isHiddenCta && (
            canOffer ? (
              <button onClick={() => setShowOffer(true)} className={ui.btnPrimary}>Send an offer</button>
            ) : isLoggedOut ? (
              <button onClick={() => navigate('/cappe/login')} className={ui.btnPrimary}>Work with {profile.display_name}</button>
            ) : null
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5">
          {profile.niches.map((n) => <span key={n} className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">{n}</span>)}
        </div>

        {profile.bio && <p className="mt-4 max-w-2xl text-sm leading-relaxed text-zinc-300">{profile.bio}</p>}

        {profile.reach_verified && (
          <div className="mt-5 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-2.5 text-sm text-emerald-300">
            Reach verified by Gummfit {profile.reach_audited_at ? `on ${new Date(profile.reach_audited_at).toLocaleDateString()}` : ''}
          </div>
        )}

        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Socials</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {profile.socials.map((s) => (
              <a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer" className={`${ui.cardHover} flex items-center justify-between px-3 py-2.5 text-sm`}>
                <span className="flex items-center gap-2 text-zinc-200">
                  <ExternalLink className="h-3.5 w-3.5 text-zinc-500" />
                  {s.platform} · @{s.handle}
                </span>
                <span className="text-zinc-400">
                  {s.audit_status === 'verified' && s.verified_follower_count != null
                    ? <>{s.verified_follower_count.toLocaleString()} <span className="text-emerald-400">✓</span></>
                    : s.follower_count != null
                      ? <span className={ui.muted}>{s.follower_count.toLocaleString()} (self-reported)</span>
                      : null}
                </span>
              </a>
            ))}
            {profile.socials.length === 0 && <p className="text-sm text-zinc-500">No socials listed.</p>}
          </div>
        </section>

        {profile.portfolio.length > 0 && (
          <section className="mt-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Portfolio</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {profile.portfolio.map((p) => (
                <div key={p.id} className={`${ui.card} overflow-hidden`}>
                  {p.media_type === 'video' && p.media_url ? (
                    <video src={p.media_url} controls className="h-36 w-full bg-black object-cover" />
                  ) : p.media_url ? (
                    <img src={p.media_url} alt={p.title} className="h-36 w-full object-cover" />
                  ) : p.external_url ? (
                    <a href={p.external_url} target="_blank" rel="noopener noreferrer" className="flex h-36 w-full items-center justify-center bg-zinc-800 text-sm text-zinc-400">
                      <ExternalLink className="mr-1.5 h-4 w-4" /> View
                    </a>
                  ) : null}
                  <div className="p-3">
                    <p className="text-sm font-medium text-zinc-200">{p.title}</p>
                    {p.brand_name && <span className="mt-1 inline-block rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{p.brand_name}</span>}
                    {p.description && <p className="mt-1.5 text-xs text-zinc-500">{p.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {profile.rates.length > 0 && (
          <section className="mb-12 mt-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Rate card</h2>
            <table className="w-full overflow-hidden rounded-xl border border-zinc-800 text-sm">
              <thead className="bg-zinc-900 text-zinc-500">
                <tr><th className="px-3 py-2 text-left font-medium">Type</th><th className="px-3 py-2 text-left font-medium">Platform</th><th className="px-3 py-2 text-left font-medium">Price</th><th className="px-3 py-2 text-left font-medium"></th></tr>
              </thead>
              <tbody className="divide-y divide-zinc-800">
                {profile.rates.map((r) => (
                  <tr key={r.id}>
                    <td className="px-3 py-2 text-zinc-300">{r.deliverable_type}</td>
                    <td className="px-3 py-2 text-zinc-300">{r.platform}</td>
                    <td className="px-3 py-2 text-zinc-300">{fmtCents(r.price_cents)}</td>
                    <td className="px-3 py-2">{r.negotiable && <span className={badgeFor('draft')}>negotiable</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>

      {showOffer && (
        <SendOfferSheet profile={profile} onClose={() => setShowOffer(false)} onSent={() => setShowOffer(false)} />
      )}

      <div className="pb-8 text-center">
        <Link to={creatorPaths.directory} className="text-xs text-zinc-600 hover:text-zinc-400">&larr; Back to directory</Link>
      </div>
    </div>
  )
}
