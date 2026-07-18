import { type CSSProperties } from 'react'
import { QrCode } from 'lucide-react'
import type { Branding } from './types'
import { textOn } from './helpers'

// Live poster mock — same layout as ir_report_poster.build_report_poster_pdf:
// primary background, secondary corner brackets, white QR card, fixed Matcha wordmark.
export function PosterPreview({ primary, secondary }: Branding) {
  const text = textOn(primary)
  const corner = (pos: CSSProperties): CSSProperties => ({
    position: 'absolute', height: 14, width: 14, ...pos,
  })
  return (
    <div
      className="relative rounded-lg overflow-hidden"
      style={{ background: primary, width: 150, height: 194, color: text, fontFamily: 'Georgia, serif' }}
    >
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-2 text-center">
        <div className="text-[9px] font-bold tracking-wide leading-tight">SUBMIT AN INCIDENT</div>
        <div className="relative" style={{ width: 78, height: 78 }}>
          <span style={corner({ top: 0, left: 0, borderTop: `2px solid ${secondary}`, borderLeft: `2px solid ${secondary}`, borderTopLeftRadius: 3 })} />
          <span style={corner({ top: 0, right: 0, borderTop: `2px solid ${secondary}`, borderRight: `2px solid ${secondary}`, borderTopRightRadius: 3 })} />
          <span style={corner({ bottom: 0, left: 0, borderBottom: `2px solid ${secondary}`, borderLeft: `2px solid ${secondary}`, borderBottomLeftRadius: 3 })} />
          <span style={corner({ bottom: 0, right: 0, borderBottom: `2px solid ${secondary}`, borderRight: `2px solid ${secondary}`, borderBottomRightRadius: 3 })} />
          <div className="absolute inset-[7px] bg-white rounded flex items-center justify-center">
            <QrCode className="w-8 h-8 text-zinc-900" />
          </div>
        </div>
        <div className="leading-tight">
          <div className="text-[10px] font-bold tracking-wider">SCAN ME</div>
          <div className="text-[7px] font-bold tracking-wide">HEY-MATCHA.COM</div>
          <div className="text-[5px] uppercase tracking-wider" style={{ opacity: 0.7 }}>Powered by Matcha</div>
        </div>
      </div>
    </div>
  )
}
