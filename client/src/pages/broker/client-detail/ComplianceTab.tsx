import { Card } from '../../../components/ui'
import type { BrokerClientDetailResponse } from '../../../types/broker'

export function ComplianceTab({ compliance }: { compliance: BrokerClientDetailResponse['compliance'] }) {
  if (compliance.locations.length === 0) {
    return (
      <Card className="p-5">
        <p className="text-sm text-zinc-500">No compliance locations configured.</p>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {compliance.locations.map((loc) => (
        <Card key={loc.id} className="p-4">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className="text-sm font-medium text-zinc-200">
                {loc.name ?? `${loc.city}, ${loc.state}`}
              </h3>
              {loc.name && (
                <p className="text-xs text-zinc-500 mt-0.5">{loc.city}, {loc.state}</p>
              )}
            </div>
            <span className="text-xs text-zinc-400">
              {loc.total_requirements} req.
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(loc.categories).map(([cat, count]) => (
              <span
                key={cat}
                className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${
                  count === 0
                    ? 'bg-zinc-800 text-zinc-500'
                    : 'bg-zinc-800 text-zinc-300'
                }`}
              >
                {cat}: <span className="">{count}</span>
              </span>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}
