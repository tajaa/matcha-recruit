import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, MapPin, MapPinned, ArrowRight, ArrowLeft } from 'lucide-react'
import { cappeApi, fetchCappeDirectoryCategories } from '../api'
import TemplateGallery from '../components/TemplateGallery'
import { useCappeMe } from '../hooks/useCappeMe'
import { CAPPE_HOST } from '../host'
import { creatorPaths } from '../creators/creatorPaths'
import { subdomainPreview } from '../utils/slug'
import type { CappeDirectoryCategory, CappeSite, CappeLocation, CappeTemplateSummary } from '../types'

// Post-signup business-setup wizard. account_type is already chosen at signup;
// this asks the questions that shape the rest of the product — single vs
// multi-location, the name, what kind of business it is — then how to start:
// blank or from a template. The category is asked ONCE here and used twice:
// it sorts the template shelf and seeds the Discover listing, so nobody is
// asked again on the directory card. The template choice has to live here: the
// Free plan includes one site, so a wizard that only made blank sites spent it
// before the gallery was reachable. Mounted at /cappe/onboarding inside
// CappeLayout; CappeSites redirects here on first run (zero sites).
type Mode = 'single' | 'multi'
type Step = 1 | 2 | 3 | 4

// The Discover taxonomy is business-shaped; a personal site picks from the
// creative slice of it so the question still makes sense.
const PERSONAL_CATEGORIES = new Set(['art-design', 'photo-video', 'music-audio', 'tech', 'education', 'other'])

export default function CappeOnboardingWizard() {
  const navigate = useNavigate()
  const { account } = useCappeMe()

  useEffect(() => {
    if (account?.account_type === 'creator') {
      navigate(creatorPaths.home, { replace: true })
    }
  }, [account, navigate])

  const [step, setStep] = useState<Step>(1)
  const [mode, setMode] = useState<Mode | null>(null)
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('')
  const [categories, setCategories] = useState<CappeDirectoryCategory[] | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Which template is being cloned, when the site is not starting blank.
  const [templateSlug, setTemplateSlug] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetchCappeDirectoryCategories()
      .then((r) => { if (alive) setCategories(r.categories) })
      // The question is a nicety, not a gate: with no taxonomy the person
      // skips it and the setup concierge can still infer a listing later.
      .catch(() => { if (alive) setCategories([]) })
    return () => { alive = false }
  }, [])

  if (account?.account_type === 'creator') {
    return (
      <div className="flex min-h-full items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  const personal = account?.account_type === 'personal'
  const slugPreview = subdomainPreview(name)
  const categoryChoices = (categories ?? []).filter((c) => !personal || PERSONAL_CATEGORIES.has(c.slug))

  async function finish(template: CappeTemplateSummary | null) {
    if (!name.trim() || submitting) return
    setSubmitting(true)
    setTemplateSlug(template?.slug ?? null)
    setError(null)
    try {
      const site = template
        ? await cappeApi.post<CappeSite>('/sites/from-template', {
            template_slug: template.slug,
            name: name.trim(),
            is_multi_location: mode === 'multi',
            ...(category ? { directory_category: category } : {}),
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
      setTemplateSlug(null)
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

  const TITLES: Record<Step, string> = {
    1: `Hi${account?.name ? ` ${account.name.split(' ')[0]}` : ''} — let's set up`,
    2: 'Name your business',
    3: personal ? "What's the site for?" : 'What kind of business is it?',
    4: 'How do you want to start?',
  }
  const BLURBS: Record<Step, string> = {
    1: 'A couple of quick questions so we can shape everything around how you work.',
    2: 'This becomes your web address. You can change it later.',
    3: personal
      ? "We'll put the templates made for it first."
      : "We'll put the templates made for it first, and list you under it in Discover.",
    4: 'Pick a design to start from, or begin with an empty site. Either way, everything is editable.',
  }
  const width = step === 4 ? 'max-w-4xl' : step === 3 ? 'max-w-xl' : 'max-w-md'

  return (
    <div className="flex min-h-full items-center justify-center bg-zinc-950 py-8 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4">
      <div className={`w-full ${width}`}>
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-lime-300 to-lime-500 text-lg font-bold text-zinc-950 shadow-lg shadow-lime-500/20">
            G
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{TITLES[step]}</h1>
          <p className="mt-1 text-sm text-zinc-400">{BLURBS[step]}</p>
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
          ) : step === 2 ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) setStep(3)
              }}
            >
              <label htmlFor="cappe-onboarding-name" className="mb-1 block text-sm font-medium text-zinc-300">
                {personal ? 'Your name or business name' : 'Business name'}
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
          ) : step === 3 ? (
            <>
              {categories === null ? (
                <div className="flex justify-center py-10">
                  <Loader2 className="h-5 w-5 animate-spin text-zinc-600" />
                </div>
              ) : categoryChoices.length === 0 ? (
                <p className="py-4 text-center text-sm text-zinc-500">
                  Couldn't load the category list — you can pick one later from your site's Discover settings.
                </p>
              ) : (
                <div role="group" aria-label="Business category" className="grid grid-cols-2 gap-2">
                  {categoryChoices.map((c) => {
                    const active = category === c.slug
                    return (
                      <button
                        key={c.slug}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setCategory(active ? null : c.slug)}
                        className={`rounded-xl border px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                          active
                            ? 'border-lime-400 bg-lime-300/10 text-lime-200'
                            : 'border-zinc-700 bg-zinc-950 text-zinc-200 hover:border-zinc-500'
                        }`}
                      >
                        {c.label}
                      </button>
                    )
                  })}
                </div>
              )}
              <div className="mt-5 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800"
                >
                  <ArrowLeft className="h-4 w-4" /> Back
                </button>
                <button
                  type="button"
                  onClick={() => { setCategory(null); setStep(4) }}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-200"
                >
                  Skip for now
                </button>
                <button
                  type="button"
                  disabled={!category}
                  onClick={() => setStep(4)}
                  className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-lime-300 disabled:opacity-50"
                >
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setStep(3)}
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
                  {submitting && templateSlug === null && <Loader2 className="h-4 w-4 animate-spin" />}
                  Start with a blank site
                </button>
              </div>
              {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
              <TemplateGallery
                category={category}
                busySlug={templateSlug}
                disabled={submitting}
                onPick={(t) => finish(t)}
              />
            </>
          )}
        </div>

        <div className="mt-4 flex items-center justify-center gap-1.5">
          {([1, 2, 3, 4] as Step[]).map((n) => (
            <span key={n} className={`h-1.5 w-1.5 rounded-full ${step === n ? 'bg-lime-400' : 'bg-zinc-700'}`} />
          ))}
        </div>
      </div>
    </div>
  )
}
