const HEADLINES = [
  { text: 'Walmart — $60M EEOC settlement for pregnancy discrimination', tag: 'EEOC' },
  { text: 'Wells Fargo — $3.7B CFPB fine for consumer and employee abuses', tag: 'CFPB' },
  { text: 'Norfolk Southern — $600M+ costs from East Palestine safety violations', tag: 'NTSB' },
  { text: 'Activision Blizzard — $54.8M DFEH settlement for workplace harassment', tag: 'DFEH' },
  { text: 'Dollar General — $12M+ OSHA fines for repeated safety violations', tag: 'OSHA' },
  { text: 'Boeing — $200M SEC settlement for misleading safety disclosures', tag: 'SEC' },
  { text: 'FedEx — $365M settlement for worker misclassification claims', tag: 'DOL' },
  { text: 'Tesla — $3.2M EEOC verdict for racial harassment at Fremont plant', tag: 'EEOC' },
  { text: 'Amazon — $5.9M OSHA penalties for warehouse safety violations', tag: 'OSHA' },
  { text: 'Meta — €1.2B EU GDPR fine for data transfer violations', tag: 'GDPR' },
  { text: "McDonald's — $26M settlement for wage theft class action", tag: 'DOL' },
  { text: 'Starbucks — 200+ NLRB violations for union-busting nationwide', tag: 'NLRB' },
  { text: 'J&J — $8.9B talc liability drove subsidiary Chapter 11 filing', tag: 'BANKRUPTCY' },
  { text: 'Dollar Tree — $13.6M OSHA fines as repeat serious violator', tag: 'OSHA' },
  { text: 'SpaceX — DOJ sued for citizenship discrimination in hiring', tag: 'DOJ' },
  { text: 'Steward Health Care files Chapter 11 — largest private hospital operator', tag: 'BANKRUPTCY' },
]

const ITEMS = [...HEADLINES, ...HEADLINES]

export function ComplianceTicker() {
  return (
    <div
      className="fixed top-0 left-0 right-0 z-[60] overflow-hidden"
      style={{
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
            color: '#d7ba7d',
          }}
        >
          <span className="relative inline-flex w-1.5 h-1.5">
            <span
              className="absolute inline-flex w-full h-full rounded-full animate-ping"
              style={{ backgroundColor: '#d7ba7d', opacity: 0.5 }}
            />
            <span
              className="relative inline-flex rounded-full w-1.5 h-1.5"
              style={{ backgroundColor: '#d7ba7d' }}
            />
          </span>
          Live enforcement
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
                    color: '#9a8a70',
                    border: '1px solid rgba(154,138,112,0.35)',
                  }}
                >
                  {item.tag}
                </span>
                <span
                  className="text-[13px]"
                  style={{ color: 'rgba(228,222,210,0.7)' }}
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
