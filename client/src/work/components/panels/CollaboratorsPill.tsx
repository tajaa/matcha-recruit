import { avatarColor } from '../../utils/avatarColor'
import type { PresenceMember } from '../../api/projectSocket'

interface Props {
  members: PresenceMember[]
  selfId?: string
}

const PAGE_LABELS: Record<string, string> = {
  sections: 'Sections',
  pipeline: 'Pipeline',
  chat: 'Chat',
  presentation: 'Presentation',
}

function pageLabel(pageKey: string | null): string {
  if (!pageKey) return 'Idle'
  if (pageKey.startsWith('sections:')) return 'Sections'
  return PAGE_LABELS[pageKey] ?? pageKey
}

/**
 * Header pill showing every user currently in this project, with a
 * tooltip listing which sub-tab they're on. Avatars are bordered with the
 * user's deterministic `avatarColor()` so the color matches their cursor
 * + caret marker on the active surface.
 */
export default function CollaboratorsPill({ members, selfId }: Props) {
  const others = members.filter((m) => m.id !== selfId)
  if (others.length === 0) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ display: 'flex', marginLeft: 4 }}>
        {others.slice(0, 5).map((m, idx) => {
          const color = avatarColor(m.id)
          const initial = (m.name || m.email || '?').charAt(0).toUpperCase()
          return (
            <div
              key={m.id}
              title={`${m.name} — ${pageLabel(m.page_key)}`}
              style={{
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: m.avatar_url ? 'transparent' : color,
                border: `2px solid ${color}`,
                marginLeft: idx === 0 ? 0 : -6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#000',
                fontSize: 10,
                fontWeight: 600,
                overflow: 'hidden',
                cursor: 'default',
              }}
            >
              {m.avatar_url ? (
                <img
                  src={m.avatar_url}
                  alt={m.name}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                initial
              )}
            </div>
          )
        })}
        {others.length > 5 && (
          <div
            style={{
              width: 22,
              height: 22,
              borderRadius: '50%',
              background: 'rgba(255,255,255,0.15)',
              border: '2px solid rgba(255,255,255,0.3)',
              marginLeft: -6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: 9,
              fontWeight: 600,
            }}
            title={others.slice(5).map((m) => m.name).join(', ')}
          >
            +{others.length - 5}
          </div>
        )}
      </div>
      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)' }}>
        {others.length === 1 ? '1 active' : `${others.length} active`}
      </span>
    </div>
  )
}
