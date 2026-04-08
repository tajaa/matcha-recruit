const HEADLINES = [
  { text: 'Walmart — $60M EEOC settlement for pregnancy discrimination', tag: 'EEOC', color: '#f59e0b' },
  { text: 'Wells Fargo — $3.7B CFPB fine for consumer and employee abuses', tag: 'CFPB', color: '#ef4444' },
  { text: 'Norfolk Southern — $600M+ costs from East Palestine safety violations', tag: 'NTSB', color: '#ef4444' },
  { text: 'Activision Blizzard — $54.8M DFEH settlement for workplace harassment', tag: 'DFEH', color: '#f59e0b' },
  { text: 'Dollar General — $12M+ OSHA fines for repeated safety violations', tag: 'OSHA', color: '#f59e0b' },
  { text: 'Boeing — $200M SEC settlement for misleading safety disclosures', tag: 'SEC', color: '#ef4444' },
  { text: 'FedEx — $365M settlement for worker misclassification claims', tag: 'DOL', color: '#ef4444' },
  { text: 'Tesla — $3.2M EEOC verdict for racial harassment at Fremont plant', tag: 'EEOC', color: '#f59e0b' },
  { text: 'Amazon — $5.9M OSHA penalties for warehouse safety violations', tag: 'OSHA', color: '#f59e0b' },
  { text: 'Meta — €1.2B EU GDPR fine for data transfer violations', tag: 'GDPR', color: '#ef4444' },
  { text: 'McDonald\'s — $26M settlement for wage theft class action', tag: 'DOL', color: '#f59e0b' },
  { text: 'Starbucks — 200+ NLRB violations for union-busting nationwide', tag: 'NLRB', color: '#f59e0b' },
  { text: 'J&J — $8.9B talc liability drove subsidiary Chapter 11 filing', tag: 'BANKRUPTCY', color: '#ef4444' },
  { text: 'Dollar Tree — $13.6M OSHA fines as repeat serious violator', tag: 'OSHA', color: '#f59e0b' },
  { text: 'SpaceX — DOJ sued for citizenship discrimination in hiring', tag: 'DOJ', color: '#ef4444' },
  { text: 'Steward Health Care files Chapter 11 — largest private hospital operator', tag: 'BANKRUPTCY', color: '#ef4444' },
]

// Double the list for seamless infinite scroll
const ITEMS = [...HEADLINES, ...HEADLINES]

export function ComplianceTicker() {
  return (
    <div
      className="fixed top-[72px] left-0 right-0 z-40 overflow-hidden border-b border-zinc-800/60"
      style={{ background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)' }}
    >
      <div className="flex items-center">
        {/* Static label */}
        <div
          className="shrink-0 px-4 py-1.5 border-r border-zinc-800/60 text-[10px] font-medium uppercase tracking-[0.15em] text-red-500"
          style={{ fontFamily: "'Space Mono', monospace" }}
        >
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 mr-2 animate-pulse" />
          LIVE
        </div>

        {/* Scrolling ticker */}
        <div className="overflow-hidden flex-1">
          <div
            className="flex items-center gap-8 whitespace-nowrap animate-[ticker_90s_linear_infinite]"
            style={{ width: 'max-content' }}
          >
            {ITEMS.map((item, i) => (
              <span key={i} className="inline-flex items-center gap-2 py-1.5">
                <span
                  className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-sm"
                  style={{
                    color: item.color,
                    border: `1px solid ${item.color}40`,
                    fontFamily: "'Space Mono', monospace",
                  }}
                >
                  {item.tag}
                </span>
                <span className="text-[13px] text-zinc-500" style={{ fontFamily: "'Inter', sans-serif" }}>
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
