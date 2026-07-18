import type { Props } from './CreateChannelModal/types'
import { SimpleForm } from './CreateChannelModal/SimpleForm'
import { WizardForm } from './CreateChannelModal/WizardForm'

/* ─── Main export ─── */

export default function CreateChannelModal({ onClose, onCreated, canCreatePaid = false }: Props) {
  if (canCreatePaid) {
    return <WizardForm onClose={onClose} onCreated={onCreated} />
  }
  return <SimpleForm onClose={onClose} onCreated={onCreated} />
}
