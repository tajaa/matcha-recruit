import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, MapPin, MapPinned, ArrowRight, ArrowLeft } from 'lucide-react'
import { cappeApi } from '../api'
import TemplateGallery from '../components/TemplateGallery'
import { useCappeMe } from '../hooks/useCappeMe'
import { CAPPE_HOST } from '../host'
import { creatorPaths } from '../creators/creatorPaths'
import { subdomainPreview } from '../utils/slug'
import type { CappeSite, CappeLocation, CappeTemplateSummary } from '../types'

// Post-signup business-setup wizard. account_type is already chosen at signup;
// this asks the one question that shapes the rest of the product — single vs
// multi-location — then the name, then how to start: blank or from a template.
// The template choice has to live here: the Free plan includes one site, so a
// wizard that only made blank sites spent it before the gallery was reachable.
// Mounted at /cappe/onboarding inside CappeLayout; CappeSites redirects here on
// first run (zero sites).
type Mode = 'single' | 'multi'

export default function CappeOnboardingWizard() {
  const navigate = useNavigate()
  const { account } = useCappeMe()

  useEffect(() => {
    if (account?.account_type === 'creator') {
      navigate(creatorPaths.home, { replace: true })
    }
  }, [account, navigate])

  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [mode, setMode] = useState<Mode | null>(null)
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // Which template is being cloned, when the site is not starting blank.
  const [templateId, setTemplateId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (account?.account_type === 'creator') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  const slugPreview = subdomainPreview(name)

  async function finish(template: CappeTemplateSummary | null) {
    if (!name.trim() || submitting) return
    setSubmitting(true)
    setTemplateId(template?.id ?? null)
    setError(null)
    try {
      const site = template
        ? await cappeApi.post<CappeSite>('/sites/from-template', {
            template_id: template.id,
            name: name.trim(),
            is_multi_location: mode === 'multi',
          })
        : await cappeApi.post<CappeSite>('/sites', {
            name: name.trim(),
            source_type: 'blank',
            is_multi_location: mode === 'multi',
          })
      if (mode === 'multi') {
        // Seed the first branch; the rest are added in the Locations manager.
        await cappeApi
          .post<CappeLocation>(`/sites/${site.id}/locations`, {
            name: branch.trim() || 'Main',
            is_default: true,
          })
          .catch(() => {
            /* non-fatal: they can add branches in the Locations manager */
          })
        navigate(`/cappe/sites/${site.id}/locations`, { replace: true })
      } else {
        navigate(`/cappe/sites/${site.id}`, { replace: true, state: { fromOnboarding: true } })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create your site. Try again.')
      setSubmitting(false)
      setTemplateId(null)
    }
  }

  const MODES: { value: Mode; icon: typeof MapPin; title: string; blurb: string }[] = [
    {
      value: 'single',
      icon: MapPin,
      title: 'One location',
      blurb: 'A single shop, studio or office. One set of hours, one map.',
    },
    {
      value: 'multi',
      icon: MapPinned,
      title: 'Multiple locations',
      blurb: 'Branches with their own staff, hours, bookings and map info.',
    },
  ]

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
      <div className={`w-full ${step === 3 ? 'max-w-4xl py-10' : 'max-w-md'}`}>
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-lime-300 to-lime-500 text-lg font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
            G
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            {step === 1
              ? `Hi${account?.name ? ` ${account.name.split(' ')[0]}` : ''} — let's set up`
              : step === 2 ? 'Name your business' : 'How do you want to start?'}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {step === 1
              ? 'A couple of quick questions so we can shape everything around how you work.'
              : step === 2
                ? 'This becomes your web address. You can change it later.'
                : 'Pick a design to start from, or begin with an empty site. Either way, everything is editable.'}
          </p>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-xl shadow-black/40">
          {step === 1 ? (
            <>
              <label className="mb-3 block text-sm font-medium text-zinc-300">
                Do you have one location, or more than one?
              </label>
              <div className="grid gap-2">
                {MODES.map(({ value, icon: Icon, title, blurb }) => {
                  const active = mode === value
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setMode(value)}
                      aria-pressed={active}
                      className={`flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors ${
                        active ? 'border-lime-400 bg-lime-300/10' : 'border-zinc-700 bg-zinc-950 hover:border-zinc-500'
                      }`}
                    >
                      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${active ? 'text-lime-300' : 'text-zinc-500'}`} />
                      <span>
                        <span className={`block text-sm font-medium ${active ? 'text-lime-200' : 'text-zinc-200'}`}>{title}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-zinc-500">{blurb}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
              <button
                type="button"
                disabled={!mode}
                onClick={() => setStep(2)}
                className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-50"
              >
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </>
          ) : step === 3 ? (
            <>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  disabled={submitting}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
                >
                  <ArrowLeft className="h-4 w-4" /> Back
                </button>
                <button
                  type="button"
                  onClick={() => finish(null)}
                  disabled={submitting}
                  className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
                >
                  {submitting && templateId === null && <Loader2 className="h-4 w-4 animate-spin" />}
                  Start with a blank site
                </button>
              </div>
              {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
              <TemplateGallery
                accountType={account?.account_type}
                busyId={templateId}
                disabled={submitting}
                onPick={(t) => finish(t)}
              />
            </>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) setStep(3)
              }}
            >
              <label htmlFor="cappe-onboarding-name" className="mb-1 block text-sm font-medium text-zinc-300">
                {account?.account_type === 'personal' ? 'Your name or business name' : 'Business name'}
              </label>
              <input
                id="cappe-onboarding-name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Lumière Skincare Spa"
                maxLength={255}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-400 focus:ring-1 focus:ring-lime-400"
              />
              <p className="mt-2 min-h-[1rem] text-xs text-zinc-500">
                {name.trim() && (
                  <>
                    Your site: <span className="text-lime-400">{slugPreview}.{CAPPE_HOST}</span>{' '}
                    (we'll adjust it slightly if that address is taken)
                  </>
                )}
              </p>

              {mode === 'multi' && (
                <div className="mt-4">
                  <label className="mb-1 block text-sm font-medium text-zinc-300">Your first branch</label>
                  <input
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="e.g. Downtown"
                    maxLength={255}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-400 focus:ring-1 focus:ring-lime-400"
                  />
                  <p className="mt-1.5 text-xs text-zinc-500">You'll add the rest right after — with their own hours, map and staff.</p>
                </div>
              )}

              <div className="mt-5 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800"
                >
                  <ArrowLeft className="h-4 w-4" /> Back
                </button>
                <button
                  type="submit"
                  disabled={!name.trim()}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-50"
                >
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </form>
          )}
        </div>

        <div className="mt-4 flex items-center justify-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${step === 1 ? 'bg-lime-400' : 'bg-zinc-700'}`} />
          <span className={`h-1.5 w-1.5 rounded-full ${step === 2 ? 'bg-lime-400' : 'bg-zinc-700'}`} />
          <span className={`h-1.5 w-1.5 rounded-full ${step === 3 ? 'bg-lime-400' : 'bg-zinc-700'}`} />
        </div>
      </div>
    </div>
  )
}
