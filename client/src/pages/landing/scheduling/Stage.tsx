import { lazy, Suspense, useRef, type ComponentType, type CSSProperties, type ReactNode } from 'react'
import { useIdle, useInView, useNarrow } from './hooks'
import { Poster, StageLayout } from './StageFrame'
import type { Variant } from './timeline'

// Remotion (player + runtime) is its own chunk, fetched only when a stage is
// about to be seen. Each composition is a further chunk behind `load`.
const RemotionStage = lazy(() => import('./RemotionStage'))

export type CompositionLoader = () => Promise<{ default: ComponentType<{ variant: Variant }> }>

export type StageProps = {
  /** Module-level (stable) dynamic import of the composition. */
  load: CompositionLoader
  sizes: Record<Variant, { w: number; h: number }>
  durationInFrames: number
  /** Frame shown instead of playback when motion is reduced. */
  stillFrame: number
  /** Describes what the animation shows, for screen readers. */
  label: string
  caption?: ReactNode
  /** Load right after first paint (above the fold) instead of on approach. */
  eager?: boolean
  mediaClassName?: string
  mediaStyle?: CSSProperties
  decor?: ReactNode
}

export default function Stage(props: StageProps) {
  const variant: Variant = useNarrow() ? 'narrow' : 'wide'
  const size = props.sizes[variant]
  const ref = useRef<HTMLDivElement>(null)
  const near = useInView(ref, '600px 0px 600px 0px', 0)
  const idle = useIdle(Boolean(props.eager))
  const load = near || (props.eager && idle)

  const poster = (
    <StageLayout
      media={<Poster width={size.w} height={size.h} />}
      control={null}
      caption={props.caption}
      mediaClassName={props.mediaClassName}
      mediaStyle={props.mediaStyle}
      decor={props.decor}
    />
  )

  return (
    <div ref={ref}>
      {load ? (
        <Suspense fallback={poster}>
          <RemotionStage {...props} variant={variant} />
        </Suspense>
      ) : (
        poster
      )}
    </div>
  )
}
