import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Search, Star } from 'lucide-react'
import { tellusPublicGet, tellusPublicPost } from '../api/tellusClient'
import { Button, Card, ErrorText, Input } from '../components/ui'
import type { PlaceAutocompleteResult, PlaceCreateResponse, PlaceSearchResult } from '../api/types'

export default function Places() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [city, setCity] = useState('')
  const [results, setResults] = useState<PlaceSearchResult[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchErr, setSearchErr] = useState('')

  const [addName, setAddName] = useState('')
  const [addCity, setAddCity] = useState('')
  const [addState, setAddState] = useState('')
  const [website, setWebsite] = useState('') // honeypot
  const [adding, setAdding] = useState(false)
  const [addErr, setAddErr] = useState('')

  // Google Places autocomplete on the add-form name field. Silent no-op when
  // GOOGLE_MAPS_API_KEY is unset server-side — /places/autocomplete just
  // returns [] and the form behaves exactly like manual entry.
  const [suggestions, setSuggestions] = useState<PlaceAutocompleteResult[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [pickedPlaceId, setPickedPlaceId] = useState<string | null>(null)

  useEffect(() => {
    if (pickedPlaceId || addName.trim().length < 2) { setSuggestions([]); return }
    const t = setTimeout(() => {
      const params = new URLSearchParams({ q: addName.trim() })
      if (addCity.trim()) params.set('city', addCity.trim())
      tellusPublicGet<PlaceAutocompleteResult[]>(`/places/autocomplete?${params.toString()}`)
        .then(setSuggestions)
        .catch(() => setSuggestions([])) // autocomplete is best-effort — never blocks manual entry
    }, 300)
    return () => clearTimeout(t)
  }, [addName, addCity, pickedPlaceId])

  function pickSuggestion(s: PlaceAutocompleteResult) {
    setAddName(s.name)
    setPickedPlaceId(s.place_id)
    setShowSuggestions(false)
    // Best-effort city/state prefill from "123 Main St, Springfield, IL" —
    // the server re-resolves the real address from Place Details regardless,
    // this just saves the user retyping it.
    const parts = (s.secondary_text || '').split(',').map((p) => p.trim()).filter(Boolean)
    if (parts.length >= 2) {
      setAddCity(parts[parts.length - 2])
      setAddState(parts[parts.length - 1])
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault()
    if (!q.trim()) return
    setSearching(true); setSearchErr('')
    try {
      const params = new URLSearchParams({ q: q.trim() })
      if (city.trim()) params.set('city', city.trim())
      const r = await tellusPublicGet<PlaceSearchResult[]>(`/places/search?${params.toString()}`)
      setResults(r)
    } catch (e) {
      setSearchErr(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  async function addPlace(e: React.FormEvent) {
    e.preventDefault()
    if (!addName.trim() || !addCity.trim()) return
    setAdding(true); setAddErr('')
    try {
      const res = await tellusPublicPost<PlaceCreateResponse>('/places', {
        name: addName.trim(), city: addCity.trim(), state: addState.trim() || null,
        google_place_id: pickedPlaceId, website,
      })
      if (res.intake_token) navigate('/i/' + res.intake_token)
      else navigate('/b/' + res.slug)
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : 'Could not add this place')
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-6 text-center">
        <h1 className="text-xl font-bold">Find a place to review</h1>
        <p className="mt-1 text-sm text-tu-dim">Search any store or brand — leave feedback even if they haven't joined Tell-Us yet.</p>
      </div>

      <Card>
        <form onSubmit={search} className="space-y-3">
          <Input label="Place name" required value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Blue Bottle Coffee" />
          <Input label="City (optional)" value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Austin" />
          <ErrorText>{searchErr}</ErrorText>
          <Button type="submit" loading={searching} className="w-full">
            <Search className="h-4 w-4" /> Search
          </Button>
        </form>
      </Card>

      {results !== null && (
        <div className="mt-4 space-y-2">
          {results.length === 0 ? (
            <p className="text-center text-sm text-tu-dim">No matches. Add it below.</p>
          ) : (
            results.map((r) => (
              <Card key={r.slug} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {r.logo_url && <img src={r.logo_url} alt="" className="h-10 w-10 rounded-lg object-cover" />}
                  <div>
                    <p className="text-sm font-semibold">{r.name}</p>
                    <p className="text-xs text-tu-faint">
                      {[r.city, r.state].filter(Boolean).join(', ')}
                      {r.review_count > 0 && (
                        <span className="ml-1 inline-flex items-center gap-0.5">
                          · <Star className="h-3 w-3 fill-tu-accent text-tu-accent" /> {r.review_count}
                        </span>
                      )}
                      {!r.claimed && <span className="ml-1">· unclaimed</span>}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Link to={`/b/${r.slug}`} className="text-xs font-semibold text-tu-accent hover:underline">See reviews</Link>
                  {!r.claimed && r.intake_token && (
                    <Link to={`/i/${r.intake_token}`} className="text-xs font-semibold text-tu-accent hover:underline">Leave feedback</Link>
                  )}
                </div>
              </Card>
            ))
          )}
        </div>
      )}

      <Card className="mt-6">
        <h2 className="text-sm font-semibold">Can't find it?</h2>
        <p className="mt-0.5 text-xs text-tu-dim">Add it and leave feedback right away.</p>
        <form onSubmit={addPlace} className="mt-3 space-y-3">
          <div className="relative">
            <Input
              label="Place name" required value={addName}
              onChange={(e) => {
                setAddName(e.target.value)
                setPickedPlaceId(null) // manual edit invalidates a prior pick
                setShowSuggestions(true)
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
              autoComplete="off"
            />
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-tu-border bg-tu-bg shadow-lg">
                {suggestions.map((s) => (
                  <button
                    key={s.place_id} type="button"
                    onMouseDown={() => pickSuggestion(s)}
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-tu-panel2/60"
                  >
                    <div className="text-tu-text">{s.name}</div>
                    {s.secondary_text && <div className="text-xs text-tu-faint">{s.secondary_text}</div>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label="City" required value={addCity} onChange={(e) => setAddCity(e.target.value)} />
            <Input label="State" value={addState} onChange={(e) => setAddState(e.target.value)} placeholder="TX" />
          </div>
          {/* Honeypot — hidden from humans, bots fill it. */}
          <input type="text" value={website} onChange={(e) => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off"
            className="hidden" aria-hidden="true" />
          <ErrorText>{addErr}</ErrorText>
          <Button type="submit" loading={adding} variant="soft" className="w-full">Add this place</Button>
        </form>
      </Card>
    </div>
  )
}

