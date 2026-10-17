import { AdminTabs } from '../../../../components/admin/AdminTabs'
import type { Newsletter, Tab } from './types'

type Props = {
  tab: Tab
  editingId: string | null
  newsletters: Newsletter[]
  onTabChange: (next: Tab) => void
}

export function NewsletterTabsNav({ tab, editingId, newsletters, onTabChange }: Props) {
  const drafts = newsletters.filter((newsletter) => newsletter.status === 'draft').length
  return <AdminTabs label="Newsletter views" value={tab} onChange={onTabChange} options={
    (['ideas', 'subscribers', 'newsletters', 'compose', 'tags', 'templates'] as const).map((value) => ({
      value,
      label: value === 'compose' ? (editingId ? 'Edit Draft' : 'Compose')
        : <>{value.charAt(0).toUpperCase() + value.slice(1)}{value === 'newsletters' && drafts > 0 && <span className="font-mono text-xs text-zinc-500">{drafts}</span>}</>,
    }))
  } />
}
