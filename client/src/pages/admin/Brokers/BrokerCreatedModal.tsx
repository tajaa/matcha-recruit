import { Button, Modal } from '../../../components/ui'
import type { CreateResult } from './types'

type BrokerCreatedModalProps = {
  result: CreateResult | null
  onClose: () => void
}

export function BrokerCreatedModal({ result, onClose }: BrokerCreatedModalProps) {
  return (
    <Modal open={!!result} onClose={onClose} title="Broker Created" width="md">
      {result && (
        <div className="space-y-4">
          <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">Broker</p>
            <p className="text-zinc-100 font-medium">{result.broker.name}</p>
            <p className="text-xs text-zinc-500">/{result.broker.slug}</p>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-medium">Owner Account</p>
            <p className="text-zinc-100">{result.owner.email}</p>
            {result.owner.generated_password && result.owner.password && (
              <div className="mt-2">
                <p className="text-xs text-zinc-500 mb-1">Generated password (share securely):</p>
                <code className="block bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-emerald-400 text-sm font-mono select-all">
                  {result.owner.password}
                </code>
              </div>
            )}
            {result.owner.email_sent && (
              <p className="text-xs text-emerald-500 mt-1">Welcome email sent.</p>
            )}
          </div>
          <div className="flex justify-end pt-2 border-t border-zinc-800">
            <Button size="sm" onClick={onClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
