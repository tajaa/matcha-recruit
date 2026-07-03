import type { CappeBlock } from '../../../../types/cappe'

export type FieldKind = 'text' | 'textarea' | 'select' | 'bool' | 'image' | 'video' | 'strlist' | 'list'
export type Field = {
  key: string
  label: string
  kind: FieldKind
  placeholder?: string
  options?: { value: string; label: string }[]
  item?: Field[]            // for kind 'list'
  newItem?: () => Record<string, unknown>
  addLabel?: string
}

export type BlockSchema = { label: string; fields: Field[]; make: () => CappeBlock }

export const F = (key: string, label: string, kind: FieldKind = 'text', extra: Partial<Field> = {}): Field =>
  ({ key, label, kind, ...extra })
