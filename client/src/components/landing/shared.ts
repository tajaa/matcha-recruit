export const SCAN_LINE_BG = 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(161,161,170,0.03) 2px, rgba(161,161,170,0.03) 4px)'
export const DOT_GRID_BG = 'radial-gradient(circle, rgba(161,161,170,0.4) 1px, transparent 1px)'

export const _wave = (freq: number, amp: number, phase: number) =>
  Array.from({ length: 80 }, (_, i) => {
    const x = (i / 79) * 100
    const y = 50 + Math.sin((i / 79) * Math.PI * freq + phase) * amp
    return `${x},${y}`
  }).join(' ')
export const SIGNAL_WAVE_1 = _wave(4, 15, 0)
export const SIGNAL_WAVE_2 = _wave(6, 8, 1.5)
export const SIGNAL_WAVE_3 = _wave(2.5, 20, 3)

export const PATTERN_INCIDENTS = new Set([12, 23, 34, 45, 52, 63, 33, 22])
export const RADAR_DIMS = ['Legal', 'Compliance', 'Tenure', 'Performance', 'Protected Class', 'Documentation', 'Precedent', 'Timing', 'Org Impact']
export const RADAR_VALUES = [0.7, 0.9, 0.4, 0.6, 0.85, 0.3, 0.5, 0.75, 0.65]
