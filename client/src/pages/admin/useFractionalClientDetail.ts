import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  fractionalHr,
  type ClientDetail,
  type Pro,
  type ScopeItem,
  type Task,
  type TimeEntry,
} from '../../api/admin/fractionalHr'

export type Tab = 'scope' | 'tasks' | 'time' | 'team' | 'settings'

export function useFractionalClientDetail() {
  const { clientId } = useParams<{ clientId: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ClientDetail | null>(null)
  const [scope, setScope] = useState<ScopeItem[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [time, setTime] = useState<TimeEntry[]>([])
  const [pros, setPros] = useState<Pro[]>([])
  const [tab, setTab] = useState<Tab>('scope')
  const [loading, setLoading] = useState(true)

  async function loadAll() {
    if (!clientId) return
    const [d, sc, tk, tm, pr] = await Promise.all([
      fractionalHr.getClient(clientId),
      fractionalHr.listScope(clientId),
      fractionalHr.listTasks(clientId),
      fractionalHr.listTime(clientId),
      fractionalHr.pros(),
    ])
    setDetail(d); setScope(sc.scope_items); setTasks(tk.tasks); setTime(tm.time_entries); setPros(pr.pros)
  }

  useEffect(() => {
    setLoading(true)
    loadAll().finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId])

  const refreshHeader = async () => { if (clientId) setDetail(await fractionalHr.getClient(clientId)) }
  const proOpts = [{ value: '', label: 'Unassigned' }, ...pros.map((p) => ({ value: p.id, label: p.email }))]

  return {
    navigate,
    detail,
    scope,
    setScope,
    tasks,
    setTasks,
    time,
    setTime,
    pros,
    tab,
    setTab,
    loading,
    refreshHeader,
    proOpts,
  }
}
