/** A sum a person typed into a number box: + − × ÷ and brackets, nothing else. */
export function evalSum(text: string): number | null {
  const src = text.replace(/×/g, '*').replace(/÷/g, '/').replace(/\s+/g, '')
  if (!src || !/^[\d.+\-*/()]+$/.test(src)) return null
  let i = 0
  const peek = () => src[i]
  function atom(): number {
    if (peek() === '(') { i++; const v = sum(); if (peek() !== ')') throw new Error('bracket'); i++; return v }
    if (peek() === '-') { i++; return -atom() }
    if (peek() === '+') { i++; return atom() }
    const m = /^(?:\d+\.?\d*|\.\d+)/.exec(src.slice(i))
    if (!m) throw new Error('number')
    i += m[0].length
    return parseFloat(m[0])
  }
  function product(): number {
    let v = atom()
    while (peek() === '*' || peek() === '/') { const op = src[i++]; const r = atom(); v = op === '*' ? v * r : v / r }
    return v
  }
  function sum(): number {
    let v = product()
    while (peek() === '+' || peek() === '-') { const op = src[i++]; const r = product(); v = op === '+' ? v + r : v - r }
    return v
  }
  try {
    const v = sum()
    return i === src.length && Number.isFinite(v) ? v : null
  } catch {
    return null
  }
}
