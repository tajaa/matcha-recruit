import { avatarColor } from '../../utils/avatarColor'
import type { RemoteCursor } from '../../hooks/useProjectPresence'

interface Props {
  userId: string
  name: string
  cursor: RemoteCursor
  containerWidth: number
  containerHeight: number
}

/**
 * Floating colored arrow + name label rendered at the remote user's
 * mouse position inside the same `<PresenceLayer>` the local user sees.
 *
 * Position is derived from x_pct / y_pct (0..1 of the surface bounding
 * rect) so the cursor lands on the same logical spot regardless of each
 * client's window size.
 *
 * `transition: transform 80ms linear` smooths motion between throttled
 * cursor samples (server caps at 25/sec).
 */
export default function RemoteCursorView({
  userId,
  name,
  cursor,
  containerWidth,
  containerHeight,
}: Props) {
  const color = avatarColor(userId)
  const x = Math.max(0, Math.min(containerWidth, cursor.xPct * containerWidth))
  const y = Math.max(0, Math.min(containerHeight, cursor.yPct * containerHeight))

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        transform: `translate3d(${x}px, ${y}px, 0)`,
        transition: 'transform 80ms linear',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 16 16"
        fill="none"
        style={{ display: 'block', filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))' }}
      >
        <path
          d="M2 2 L13 7 L8 8.5 L7 14 Z"
          fill={color}
          stroke="white"
          strokeWidth="1"
          strokeLinejoin="round"
        />
      </svg>
      <div
        style={{
          marginLeft: 12,
          marginTop: -2,
          padding: '2px 6px',
          background: color,
          color: '#000',
          fontSize: 10,
          fontWeight: 600,
          borderRadius: 3,
          whiteSpace: 'nowrap',
          boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
        }}
      >
        {name}
      </div>
    </div>
  )
}
