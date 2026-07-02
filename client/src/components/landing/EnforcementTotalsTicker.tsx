// Category-level enforcement aggregates — names no individual company (no bridge-burning),
// just the public annual totals agencies recover. Figures fact-checked against official
// agency reports (EEOC/DOL/OSHA/NLRB/CFPB + DLA Piper GDPR survey); keep them defensible.
// Sources:
//   EEOC FY2024 ~$700M  https://www.eeoc.gov/newsroom/eeoc-publishes-annual-performance-and-general-counsel-reports-fiscal-year-2024
//   DOL WHD FY2023 ~$274M  https://blog.dol.gov/2023/12/07/big-results-for-workers-in-2023
//   OSHA 2025 max penalties  https://www.osha.gov/news/newsreleases/osha-trade-release/20250114
//   NLRB FY2023 ~$56M  https://www.nlrb.gov/sites/default/files/attachments/pages/node-130/nlrb-fy2023-par-508.pdf
//   CFPB since 2011  https://www.consumerfinance.gov/enforcement/enforcement-by-the-numbers/
//   GDPR cumulative ~€5.9B  https://www.dlapiper.com/en-us/insights/publications/2025/01/dla-piper-gdpr-fines-and-data-breach-survey-january-2025
//   NYC DCWP ~$87M  https://www.nyc.gov/site/dca/news/035-25/
//   I-9 per-violation  https://www.uscis.gov/i-9-central/legal-requirements-and-enforcement/penalties
const HEADLINES = [
  { text: 'Discrimination, harassment & ADA — ~$700M recovered for workers (EEOC, FY2024)', tag: 'EEOC' },
  { text: 'Wage & hour / unpaid overtime — ~$274M in back wages recovered (DOL, FY2023)', tag: 'DOL' },
  { text: 'Workplace safety — up to $165K per willful violation, $16.5K per serious (OSHA, 2025)', tag: 'OSHA' },
  { text: 'Union rights / unfair labor practices — ~$56M recovered for workers (NLRB, FY2023)', tag: 'NLRB' },
  { text: 'Consumer financial compliance — ~$19.7B consumer relief + $5B penalties (CFPB, since 2011)', tag: 'CFPB' },
  { text: 'EU data privacy — ~€5.9B in GDPR fines since 2018 (EU regulators)', tag: 'GDPR' },
  { text: 'Fair workweek & sick leave — ~$87M for workers, cumulative (NYC DCWP)', tag: 'DCWP' },
  { text: 'Immigration / I-9 hiring — up to ~$27.9K per violation (DOJ / ICE)', tag: 'DOJ' },
]

const ITEMS = [...HEADLINES, ...HEADLINES]

// Default keeps the warm gold accent (the original /platform look). `mono`
// renders the ticker fully grayscale for the simpler-pages design system,
// where amber is reserved as the single emphasis color used sparingly.
const PALETTE = {
  gold: { accent: '#d7ba7d', tagText: '#c9b48e', tagBorder: 'rgba(201,180,142,0.45)' },
  mono: { accent: '#b8b2a8', tagText: 'rgba(240,236,228,0.7)', tagBorder: 'rgba(240,236,228,0.22)' },
}

export function EnforcementTotalsTicker({ mono = false }: { mono?: boolean } = {}) {
  const P = mono ? PALETTE.mono : PALETTE.gold
  return (
    <div
      className="fixed left-0 right-0 z-40 w-full overflow-hidden"
      style={{
        top: '48px',
        backgroundColor: 'var(--color-ivory-ink)',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        height: '44px',
      }}
    >
      <div className="flex items-center h-full">
        <div
          className="shrink-0 flex items-center gap-2 px-5 h-full border-r text-[11px] font-medium uppercase tracking-[0.18em]"
          style={{
            borderColor: 'rgba(255,255,255,0.08)',
            color: P.accent,
          }}
        >
          <span className="relative inline-flex w-1.5 h-1.5">
            <span
              className="absolute inline-flex w-full h-full rounded-full animate-ping"
              style={{ backgroundColor: P.accent, opacity: 0.5 }}
            />
            <span
              className="relative inline-flex rounded-full w-1.5 h-1.5"
              style={{ backgroundColor: P.accent }}
            />
          </span>
          Enforcement totals
        </div>

        <div className="overflow-hidden flex-1">
          <div
            className="flex items-center gap-10 whitespace-nowrap animate-[ticker_120s_linear_infinite]"
            style={{ width: 'max-content' }}
          >
            {ITEMS.map((item, i) => (
              <span key={i} className="inline-flex items-center gap-3">
                <span
                  className="text-[10.5px] font-medium uppercase tracking-wider px-2 py-[2px] rounded-sm"
                  style={{
                    color: P.tagText,
                    border: `1px solid ${P.tagBorder}`,
                  }}
                >
                  {item.tag}
                </span>
                <span
                  className="text-[13px]"
                  style={{ color: 'rgba(240,236,228,0.95)' }}
                >
                  {item.text}
                </span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
