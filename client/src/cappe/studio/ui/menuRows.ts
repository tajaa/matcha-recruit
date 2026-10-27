// What the right-click menu offers for what is selected (`ContextMenu.tsx`).

import type { State } from '../store/store'
import { command } from './commands'

export type Row = '-' | { id: string; label?: string } | { label: string; rows: Row[] }

const ARRANGE: Row = { label: 'Arrange', rows: ['arrange-front', 'arrange-forward', 'arrange-backward', 'arrange-back'].map((id) => ({ id })) }

/** The rows for what is selected (nothing: the page). Commands that can't
 *  apply here are left out, except the editing ones, which show greyed. */
export function menuRows(s: State): Row[] {
  const can = (id: string) => { const cmd = command(id); return !cmd.enabled || cmd.enabled(s) }
  const when = (id: string, label?: string): Row[] => (can(id) ? [{ id, ...(label ? { label } : {}) }] : [])
  const items = s.doc.items.filter((i) => s.selection.includes(i.id))
  if (!items.length) {
    return [{ id: 'paste' }, { id: 'select-all' }, { id: 'show-all' }, '-', { id: 'page-add' }, ...when('page-delete'),
      '-', { id: 'add-templates', label: 'Page templates…' }, { id: 'board' }]
  }
  const one = items.length === 1 ? items[0] : null
  const locked = items.every((i) => i.locked)
  const rows: Row[] = [{ id: 'cut' }, { id: 'copy' }, { id: 'paste' }, { id: 'duplicate' }, { id: 'delete' }]
  const own: Row[] = []
  if (one?.kind === 'text') own.push(...when('edit-text'))
  if (one?.kind === 'image') {
    own.push({ id: 'place', label: one.asset_id ? 'Replace picture…' : 'Choose a picture…' },
      ...when('edit-picture'), ...when('cut-out'), ...when('subject-front'))
  }
  own.push(...when('across-spread'), ...when('spine-clear'), ...when('link-crops'), ...when('unlink-crops'))
  if (own.length) rows.push('-', ...own)
  if (!locked) {
    const align: Row[] = ['align-left', 'align-centre', 'align-right', '-', 'align-top', 'align-middle', 'align-bottom']
      .map((id) => (id === '-' ? '-' : { id }))
    if (can('space-across')) align.push('-', { id: 'space-across' }, { id: 'space-down' })
    rows.push('-', { label: one ? 'Align to page' : 'Align', rows: align }, ARRANGE)
  }
  rows.push('-', { id: 'lock', label: locked ? 'Unlock' : 'Lock' }, { id: 'hide' })
  return rows
}
