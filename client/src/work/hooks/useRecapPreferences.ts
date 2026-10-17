import { useEffect, useState } from 'react'
import { useMe } from '../../hooks/useMe'
import { getRecapPreferences } from '../api/matchaWork/recaps'
import { useWorkSurface } from '../routes/WorkSurfaceContext'
import type { RecapPreferences } from '../types'

export function useRecapPreferences() {
  const { me, isPersonal } = useMe()
  const surface = useWorkSurface()
  const [data, setData] = useState<{ owner: string; value: RecapPreferences } | null>(null)
  const owner = me?.user.id
  useEffect(() => {
    let active = true
    if (owner && isPersonal && surface === 'espresso') {
      void getRecapPreferences().then((value) => { if (active) setData({ owner, value }) }).catch(() => {})
    }
    return () => { active = false }
  }, [owner, isPersonal, surface])
  return data && data.owner === owner && isPersonal && surface === 'espresso' ? data.value : null
}
