import { formatKey } from './helpers'

export default function RenderValue({ value }: { value: unknown }) {
  if (value == null) return <span style={{ color: '#6a737d' }}>—</span>

  if (Array.isArray(value)) {
    // Array of objects → render as mini table
    if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
      const keys = [...new Set(value.flatMap(v => Object.keys(v as Record<string, unknown>)))]
      return (
        <div className="overflow-x-auto mt-1">
          <table className="text-[10px] w-full" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {keys.map(k => (
                  <th key={k} className="text-left px-2 py-1 font-medium" style={{ color: '#6a737d', borderBottom: '1px solid #333' }}>
                    {formatKey(k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((item, i) => (
                <tr key={i}>
                  {keys.map(k => {
                    const cellVal = (item as Record<string, unknown>)[k]
                    return (
                      <td key={k} className="px-2 py-1 align-top" style={{ color: '#d4d4d4', borderBottom: '1px solid #2a2a2a' }}>
                        {cellVal == null ? '—'
                          : Array.isArray(cellVal) ? cellVal.map((v, j) => (
                              <div key={j} className="text-[10px]">
                                {typeof v === 'object' && v !== null
                                  ? Object.values(v as Record<string, unknown>).join(' · ')
                                  : String(v)}
                              </div>
                            ))
                          : typeof cellVal === 'object' ? Object.entries(cellVal as Record<string, unknown>).map(([ck, cv]) => (
                              <div key={ck} className="text-[10px]">{formatKey(ck)}: {String(cv ?? '—')}</div>
                            ))
                          : String(cellVal)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    // Array of primitives → bullet list
    return (
      <ul className="mt-0.5 space-y-0.5">
        {value.map((v, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[11px]" style={{ color: '#d4d4d4' }}>
            <span className="w-1 h-1 rounded-full bg-zinc-600 mt-1.5 shrink-0" />
            {String(v)}
          </li>
        ))}
      </ul>
    )
  }

  if (typeof value === 'object') {
    // Nested object → render as indented key-value
    return (
      <div className="mt-1 pl-3" style={{ borderLeft: '1px solid #333' }}>
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="mb-1">
            <span className="text-[10px] font-medium" style={{ color: '#9ca3af' }}>{formatKey(k)}: </span>
            <span className="text-[11px]" style={{ color: '#d4d4d4' }}>{String(v ?? '—')}</span>
          </div>
        ))}
      </div>
    )
  }

  return <span style={{ color: '#d4d4d4' }}>{String(value)}</span>
}
