import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Hash, Loader2, AlertCircle } from 'lucide-react'
import { joinByInvite } from '../../api/channels'

export default function ChannelJoinByInvite() {
  const { code } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!code) {
      setError('Invalid invite link')
      return
    }

    joinByInvite(code)
      .then((res) => {
        if (res.ok && res.channel_id) {
          navigate(`/work/channels/${res.channel_id}`, { replace: true })
        } else if (res.requires_payment && res.checkout_url) {
          window.location.href = res.checkout_url
        } else {
          setError('Unable to join channel')
        }
      })
      .catch((err) => {
        setError(err?.message || 'This invite link is invalid or expired')
      })
  }, [code, navigate])

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertCircle className="w-10 h-10 text-red-400 mx-auto" />
          <p className="text-sm text-zinc-400">{error}</p>
          <Link
            to="/work"
            className="inline-block text-sm text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            Back to Work
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center space-y-3">
        <Loader2 className="w-8 h-8 text-emerald-500 animate-spin mx-auto" />
        <div className="flex items-center gap-1.5 text-sm text-zinc-400">
          <Hash className="w-4 h-4" />
          Joining channel...
        </div>
      </div>
    </div>
  )
}
