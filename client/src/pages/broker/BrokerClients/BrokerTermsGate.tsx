import { useState } from 'react'
import { FileCheck } from 'lucide-react'
import { Button } from '../../../components/ui'
import { api } from '../../../api/client'

export function BrokerTermsGate({ onAccepted }: { onAccepted: () => void }) {
  const [accepting, setAccepting] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState('')

  async function handleAccept() {
    setAccepting(true)
    setError('')
    try {
      await api.post('/auth/broker/accept-terms', {})
      onAccepted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept terms')
    } finally {
      setAccepting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto py-8 px-4">
      <div className="flex items-center gap-3 mb-4">
        <FileCheck className="h-8 w-8 text-zinc-500" />
        <h2 className="text-lg font-semibold text-zinc-100">Broker Partner Terms of Service</h2>
      </div>
      <p className="text-sm text-zinc-400 mb-4">
        Please review the following terms before managing clients on the Matcha platform.
      </p>

      <div className="border border-zinc-700 rounded-lg bg-zinc-900/60 p-5 mb-5 max-h-80 overflow-y-auto text-sm text-zinc-300 leading-relaxed space-y-3">
        <p className="font-medium text-zinc-200">1. Scope of Services</p>
        <p>As a Matcha broker partner, you may refer client companies to the Matcha platform, assist with their onboarding, and access compliance and HR data for companies under your management. You act as an intermediary — Matcha's contractual relationship is with each client company directly.</p>

        <p className="font-medium text-zinc-200">2. Data Privacy &amp; Confidentiality</p>
        <p>You will have access to sensitive employee and company data for your referred clients. You agree to keep all client data confidential, use it only for the purposes of providing brokerage services, and comply with all applicable data protection regulations including CCPA and any state-specific privacy laws.</p>

        <p className="font-medium text-zinc-200">3. Client Relationship</p>
        <p>You may onboard clients by creating client setups and sending invitations. You must obtain proper authorization from each client company before accessing their data. Matcha reserves the right to revoke broker access to any client account if the client requests it.</p>

        <p className="font-medium text-zinc-200">4. Compliance Obligations</p>
        <p>You agree not to misrepresent Matcha's services, alter compliance recommendations, or provide legal advice to clients. Compliance data and policy suggestions provided through the platform are informational and do not constitute legal counsel.</p>

        <p className="font-medium text-zinc-200">5. Termination</p>
        <p>Either party may terminate this broker partnership at any time. Upon termination, your access to client data through the platform will be revoked. Existing client relationships with Matcha will continue independently.</p>
      </div>

      <div className="flex items-start gap-2 mb-4">
        <input
          type="checkbox"
          id="agree-terms"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 rounded border-zinc-600 bg-zinc-800 text-zinc-600 focus:ring-zinc-500"
        />
        <label htmlFor="agree-terms" className="text-sm text-zinc-400">
          I have read and agree to the Matcha Broker Partner Terms of Service
        </label>
      </div>

      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}
      <Button size="sm" onClick={handleAccept} disabled={accepting || !agreed}>
        {accepting ? 'Accepting...' : 'Accept Terms & Continue'}
      </Button>
    </div>
  )
}
