import { useState, useRef, useEffect } from 'react'
import { useInViewport } from '../hooks/useInViewport'

const MATRIX_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789!@#$%&'

export function GlitchText({ text, cycleWords, className, style }: {
  text: string
  cycleWords?: string[]
  className?: string
  style?: React.CSSProperties
}) {
  const [chars, setChars] = useState<string[]>(() =>
    text.split('').map(c => (c === ' ' || c === '.') ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)])
  )
  const [isGlitching, setIsGlitching] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const currentDisplayRef = useRef(text)
  const decodeRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const decodeInto = (target: string, onDone: () => void) => {
    if (decodeRef.current) clearInterval(decodeRef.current)
    const targetArr = target.split('')
    let progress = 0
    decodeRef.current = setInterval(() => {
      setChars(prev =>
        prev.map((_, i) => {
          const t = targetArr[i] ?? ' '
          if (t === ' ' || t === '.') return t
          if (i < progress) return t
          return MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)]
        })
      )
      progress += 0.5
      if (progress >= targetArr.length) {
        clearInterval(decodeRef.current!)
        decodeRef.current = null
        setChars(targetArr)
        currentDisplayRef.current = target
        onDone()
      }
    }, 45)
  }

  // Decode left-to-right on mount
  useEffect(() => {
    decodeInto(text, () => {})
    return () => { if (decodeRef.current) clearInterval(decodeRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Periodic glitch — paused when off-screen
  const { ref: glitchRef, isVisible: glitchVisible } = useInViewport<HTMLSpanElement>()
  const glitchVisibleRef = useRef(glitchVisible)
  glitchVisibleRef.current = glitchVisible

  useEffect(() => {
    const allPhrases = cycleWords ? [...cycleWords, text] : [text]
    let phraseIndex = 0

    const runGlitchThenDecode = (target: string, onDone: () => void) => {
      setIsGlitching(true)
      let ticks = 0
      const maxTicks = 5 + Math.floor(Math.random() * 5)
      intervalRef.current = setInterval(() => {
        const src = currentDisplayRef.current
        setChars(
          Array.from({ length: Math.max(src.length, target.length) }, (_, i) => {
            const c = src[i] ?? ' '
            if (c === ' ' || c === '.') return c
            return Math.random() > 0.35 ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)]
          })
        )
        ticks++
        if (ticks >= maxTicks) {
          clearInterval(intervalRef.current!)
          setIsGlitching(false)
          decodeInto(target, onDone)
        }
      }, 55)
    }

    const scheduleNext = () => {
      const delay = phraseIndex === 0 ? 2800 + Math.random() * 4000 : 900 + Math.random() * 600
      timeoutRef.current = setTimeout(() => {
        if (!glitchVisibleRef.current) { scheduleNext(); return }
        const target = allPhrases[phraseIndex % allPhrases.length]
        phraseIndex++
        runGlitchThenDecode(target, () => {
          if (phraseIndex < allPhrases.length) {
            scheduleNext()
          } else {
            phraseIndex = 0
            scheduleNext()
          }
        })
      }, delay)
    }

    scheduleNext()
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (decodeRef.current) clearInterval(decodeRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, cycleWords])

  return (
    <span
      ref={glitchRef}
      className={className}
      style={{
        ...style,
        textShadow: isGlitching ? '3px 0 #9ca3af, -3px 0 #d1d5db' : 'none',
        color: isGlitching ? '#6b7280' : undefined,
        transition: 'color 0.15s, text-shadow 0.15s',
      }}
    >
      {chars.join('')}
    </span>
  )
}
