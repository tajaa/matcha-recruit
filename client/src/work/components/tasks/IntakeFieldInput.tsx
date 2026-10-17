import type { IntakeFormField } from '../../types'
import { placeholder } from './tasksLogic'

/**
 * One typed field (not a file): a menu, a switch, or a text box with a hint.
 * Shared by the forms Espresso asks in chat and by an action's own fields, as
 * on the Mac (`IntakeFieldInput`). The value is always text; the form turns it
 * into what the server takes (`buildFormValues`).
 */
export default function IntakeFieldInput({ field, value, onChange, id }: {
  field: IntakeFormField
  value: string
  onChange: (value: string) => void
  /** For the label's `htmlFor`. */
  id: string
}) {
  if (field.type === 'select') {
    return (
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full max-w-xs rounded-md border border-w-line bg-w-surface px-2 py-1.5 text-xs text-w-text focus:border-w-accent focus:outline-none"
      >
        <option value="">Choose…</option>
        {(field.options ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (field.type === 'boolean') {
    const on = value === 'yes'
    return (
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={on}
        onClick={() => onChange(on ? 'no' : 'yes')}
        className={`relative h-5 w-9 rounded-full transition-colors ${on ? 'bg-w-accent' : 'bg-w-surface2'}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
      </button>
    )
  }
  return (
    <input
      id={id}
      type={field.type === 'date' ? 'date' : 'text'}
      inputMode={field.type === 'number' || field.type === 'money' ? 'decimal' : undefined}
      value={value}
      placeholder={placeholder(field)}
      onChange={(e) => onChange(e.target.value)}
      className="w-full max-w-sm rounded-md border border-w-line bg-w-surface px-2 py-1.5 text-xs text-w-text placeholder:text-w-faint focus:border-w-accent focus:outline-none"
    />
  )
}
