import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MapPin, Search, Star } from 'lucide-react'
import { tellusPublicGet, tellusPublicPost } from '../api/tellusClient'
import { Button, Card, ErrorText, Input } from '../components/ui'
import type { PlaceAutocompleteResult, PlaceCreateResponse, PlaceSearchResult } from '../api/types'

export default function Places() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [dbResults, setDbResults] = useState<PlaceSearchResult[]>([])
  const [suggestions, setSuggestions] = useState<PlaceAutocompleteResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchErr, setSearchErr] = useState('')
  const [addingPlaceId, setAddingPlaceId] = useState<string | null>(null)

  const [addName, setAddName] = useState('')
  const [addCity, setAddCity] = useState('')
  const [addState, setAddState] = useState('')
  const [website, setWebsite] = useState('') // honeypot
  const [adding, setAdding] = useState(false)
  const [addErr, setAddErr] = useState('')

  // Discards a response that resolves after a newer query has already fired
  // (out-of-order network replies) or after the component moved on.
  const seqRef = useRef(0)
  // Places API (New) session token — pairs every autocomplete keystroke with
  // the eventual Details lookup so Google bills the group as one session
  // instead of a separate call per keystroke + a separate Details call.
  const sessionRef = useRef<string>(crypto.randomUUID())

  // Live combined search on the main field: our own DB (name-only) plus
  // Google Places suggestions for anything not already on Tell-Us. Google
  // side degrades to [] silently when GOOGLE_MAPS_API_KEY is unset — the DB
  // side keeps working regardless.
  useEffect(() => {
    const query = q.trim()
    if (query.length < 2) {
      setDbResults([]); setSuggestions([]); setSearchErr(''); setSearching(false)
      return
    }
    setSearching(true)
    const t = setTimeout(() => {
      const mySeq = ++seqRef.current
      const dbParams = new URLSearchParams({ q: query })
      const acParams = new URLSearchParams({ q: query, st: sessionRef.current })
      Promise.all([
        tellusPublicGet<PlaceSearchResult[]>(`/places/search?${dbParams.toString()}`)
          .catch((e: unknown) => (e instanceof Error ? e : new Error('Search failed'))),
        tellusPublicGet<PlaceAutocompleteResult[]>(`/places/autocomplete?${acParams.toString()}`).catch(() => []),
      ]).then(([db, ac]) => {
        if (mySeq !== seqRef.current) return // a newer query already superseded this response

        if (db instanceof Error) {
          setSearchErr(/too many|429/i.test(db.message) ? 'Searching too fast — give it a second.' : 'Search failed — try again.')
          setDbResults([])
        } else {
          setSearchErr('')
          setDbResults(db)
        }

        const okDb = db instanceof Error ? [] : db
        const dbPlaceIds = new Set(okDb.map((r) => r.google_place_id).filter(Boolean))
        setSuggestions(ac.filter((s) => !dbPlaceIds.has(s.place_id)))
      }).finally(() => {
        if (mySeq === seqRef.current) setSearching(false)
      })
    }, 450)
    return () => clearTimeout(t)
  }, [q])

  async function addFromSuggestion(s: PlaceAutocompleteResult) {
    setAddingPlaceId(s.place_id); setAddErr('')
    try {
      const res = await tellusPublicPost<PlaceCreateResponse>('/places', {
        name: s.name, google_place_id: s.place_id, session_token: sessionRef.current, website,
      })
      if (res.intake_token) navigate('/i/' + res.intake_token)
      else navigate('/b/' + res.slug)
    } catch (e) {
      // Google Details couldn't verify this place right now — prefill the
      // manual form with what we already know instead of a dead-end retry.
      setAddName(s.name)
      setAddErr(e instanceof Error ? e.message : 'Could not add this place')
    } finally {
      setAddingPlaceId(null)
      sessionRef.current = crypto.randomUUID() // the session always ends on selection
    }
  }

  async function addPlace(e: React.FormEvent) {
    e.preventDefault()
    if (!addName.trim() || !addCity.trim()) return
    setAdding(true); setAddErr('')
    try {
      const res = await tellusPublicPost<PlaceCreateResponse>('/places', {
        name: addName.trim(), city: addCity.trim(), state: addState.trim() || null, website,
      })
      if (res.intake_token) navigate('/i/' + res.intake_token)
      else navigate('/b/' + res.slug)
    } catch (e) {
      setAddErr(e instanceof Error ? e.message : 'Could not add this place')
    } finally {
      setAdding(false)
    }
  }

  const showResults = q.trim().length >= 2
  const noMatches = showResults && !searching && !searchErr && dbResults.length === 0 && suggestions.length === 0

  return (
    <div className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-6 text-center">
        <h1 className="text-xl font-bold">Find a business</h1>
        <p className="mt-1 text-sm text-tu-dim">Find a business to review or message with a question.</p>
      </div>

      <Card>
        <Input
          label="Place name" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Blue Bottle Coffee" autoComplete="off"
        />
        <ErrorText>{searchErr}</ErrorText>
      </Card>

      {showResults && (
        <div className="mt-4 space-y-4">
          {dbResults.length > 0 && (
            <div className="space-y-2">
              <p className="px-1 text-xs font-semibold uppercase tracking-wide text-tu-faint">On Tell-Us</p>
              {dbResults.map((r) => (
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
                    {r.messaging_enabled && <Link to={`/b/${r.slug}?message=1`} className="text-xs font-semibold text-tu-accent hover:underline">Message</Link>}
                    {!r.claimed && r.intake_token && (
                      <Link to={`/i/${r.intake_token}`} className="text-xs font-semibold text-tu-accent hover:underline">Leave feedback</Link>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {suggestions.length > 0 && (
            <div className="space-y-2">
              <p className="px-1 text-xs font-semibold uppercase tracking-wide text-tu-faint">Add &amp; review</p>
              {suggestions.map((s) => (
                <Card key={s.place_id} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <MapPin className="h-4 w-4 shrink-0 text-tu-faint" />
                    <div>
                      <p className="text-sm font-semibold">{s.name}</p>
                      {s.secondary_text && <p className="text-xs text-tu-faint">{s.secondary_text}</p>}
                    </div>
                  </div>
                  <Button
                    size="sm" variant="soft" loading={addingPlaceId === s.place_id}
                    onClick={() => addFromSuggestion(s)}
                  >
                    Add &amp; review
                  </Button>
                </Card>
              ))}
            </div>
          )}

          {noMatches && <p className="text-center text-sm text-tu-dim">No matches. Add it manually below.</p>}
        </div>
      )}

      <ErrorText>{addErr}</ErrorText>

      <Card className="mt-6">
        <h2 className="text-sm font-semibold">Can't find it?</h2>
        <p className="mt-0.5 text-xs text-tu-dim">Add it manually and leave feedback right away.</p>
        <form onSubmit={addPlace} className="mt-3 space-y-3">
          <Input label="Place name" required value={addName} onChange={(e) => setAddName(e.target.value)} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="City" required value={addCity} onChange={(e) => setAddCity(e.target.value)} />
            <Input label="State" value={addState} onChange={(e) => setAddState(e.target.value)} placeholder="TX" />
          </div>
          {/* Honeypot — hidden from humans, bots fill it. */}
          <input type="text" value={website} onChange={(e) => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off"
            className="hidden" aria-hidden="true" />
          <Button type="submit" loading={adding} variant="soft" className="w-full">
            <Search className="h-4 w-4" /> Add this place
          </Button>
        </form>
      </Card>
    </div>
  )
}
