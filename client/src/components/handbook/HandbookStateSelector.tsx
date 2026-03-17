import { Button } from '../ui'

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
  'VA','WA','WV','WI','WY','DC',
]

type Props = {
  selected: string[]
  onChange: (states: string[]) => void
  autoDetected?: string[]
  onAutoDetect?: () => void
  multi?: boolean
}

export function HandbookStateSelector({ selected, onChange, autoDetected, onAutoDetect, multi = true }: Props) {
  function toggle(st: string) {
    if (!multi) {
      onChange([st])
      return
    }
    if (selected.includes(st)) {
      onChange(selected.filter((s) => s !== st))
    } else {
      onChange([...selected, st])
    }
  }

  return (
    <div className="space-y-3">
      {onAutoDetect && (
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={onAutoDetect}>
            Auto-detect from employees
          </Button>
          {autoDetected && autoDetected.length > 0 && (
            <span className="text-xs text-zinc-500">
              Found: {autoDetected.join(', ')}
            </span>
          )}
        </div>
      )}
      <div className="grid grid-cols-10 gap-1.5">
        {US_STATES.map((st) => (
          <button
            key={st}
            type="button"
            onClick={() => toggle(st)}
            className={`text-xs py-1.5 rounded border transition-colors ${
              selected.includes(st)
                ? 'border-emerald-600 bg-emerald-600/15 text-emerald-400'
                : autoDetected?.includes(st)
                  ? 'border-zinc-600 bg-zinc-800 text-zinc-300'
                  : 'border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300'
            }`}
          >
            {st}
          </button>
        ))}
      </div>
      {selected.length > 0 && (
        <p className="text-xs text-zinc-400">{selected.length} state(s) selected: {selected.join(', ')}</p>
      )}
    </div>
  )
}
