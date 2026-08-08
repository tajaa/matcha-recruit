import { useEffect, useRef, useState } from 'react'
import { Heart } from 'lucide-react'
import { tellusApi } from '../api/tellusClient'
import type { LikeState, LikeTarget } from '../api/types'

// Optimistic — the one deliberate exception to this app's refetch-after-
// mutation convention (see ReportDetailViewModel.swift's rationale on the
// iOS side). A like changes exactly two scalars and the endpoint hands both
// back, so reconciling from POST/DELETE's response is strictly more correct
// than a refetch: no full-page reload just to move one integer, and the
// server's authoritative count self-heals any double-tap race.
export function LikeButton({
  target, targetId, count, liked, disabled, size = 'sm', onError, onChange, onDisabledClick,
}: {
  target: LikeTarget
  targetId: string
  count: number
  liked: boolean
  disabled?: boolean
  size?: 'sm' | 'md'
  onError?: (msg: string) => void
  onChange?: (next: LikeState) => void
  // Fires instead of a no-op when disabled — e.g. PublicBrand.tsx routes an
  // anonymous viewer to login rather than letting the tap silently do nothing.
  onDisabledClick?: () => void
}) {
  const [state, setState] = useState<LikeState>({ like_count: count, liked_by_me: liked })
  const seq = useRef(0)

  // Re-sync when the parent's row changes for reasons unrelated to this
  // button (a page refetch, a different tab's write landing via polling).
  useEffect(() => {
    setState({ like_count: count, liked_by_me: liked })
  }, [count, liked])

  async function toggle() {
    if (disabled) { onDisabledClick?.(); return }
    const mySeq = ++seq.current
    const prev = state
    const optimistic: LikeState = prev.liked_by_me
      ? { like_count: Math.max(0, prev.like_count - 1), liked_by_me: false }
      : { like_count: prev.like_count + 1, liked_by_me: true }
    setState(optimistic)
    try {
      const server = prev.liked_by_me
        ? await tellusApi.delete<LikeState>(`/likes/${target}/${targetId}`)
        : await tellusApi.post<LikeState>(`/likes/${target}/${targetId}`)
      if (mySeq !== seq.current) return   // a newer tap already resolved or is in flight
      setState(server)
      onChange?.(server)
    } catch (e) {
      if (mySeq !== seq.current) return
      setState(prev)
      onError?.(e instanceof Error ? e.message : 'Failed to update like')
    }
  }

  const iconSize = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <button
      type="button"
      // A hard HTML `disabled` swallows the click entirely — only set it when
      // there's no onDisabledClick to run instead (e.g. a paused board, where
      // there's nothing useful to do on tap). With onDisabledClick (PublicBrand
      // routing an anonymous viewer to login) the button stays clickable and
      // toggle() branches on `disabled` itself.
      disabled={disabled && !onDisabledClick}
      onClick={() => void toggle()}
      className={`flex items-center gap-1.5 ${textSize} text-tu-dim hover:text-tu-accent ${disabled ? 'opacity-50' : ''} disabled:hover:text-tu-dim`}
    >
      <Heart className={`${iconSize} ${state.liked_by_me ? 'fill-tu-accent text-tu-accent' : ''}`} />
      {state.like_count > 0 ? state.like_count : ''}
    </button>
  )
}
