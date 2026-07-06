import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Employee, OnboardingProgress } from '../../types/employee'

type Filters = {
  status?: string
  search?: string
  department?: string
  employment_type?: string
}

export function useEmployees(filters: Filters = {}) {
  const [employees, setEmployees] = useState<Employee[]>([])
  const [departments, setDepartments] = useState<string[]>([])
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const filtersRef = useRef(filters)
  filtersRef.current = filters

  // Drops out-of-order employee-list responses (search-driven refetch reorders).
  const reqId = useRef(0)
  useEffect(() => () => { reqId.current++ }, [])

  // Fetch departments + onboarding progress once on mount
  useEffect(() => {
    api.get<string[]>('/employees/departments').then(setDepartments).catch(() => {})
    api.get<Record<string, OnboardingProgress>>('/employees/onboarding-progress')
      .then(setOnboardingProgress).catch(() => {})
  }, [])

  const fetchEmployees = useCallback(() => {
    const id = ++reqId.current
    setLoading(true)
    setError('')

    const params = new URLSearchParams()
    const f = filtersRef.current
    if (f.status && f.status !== 'all') params.set('employment_status', f.status)
    if (f.search) params.set('search', f.search)
    if (f.department) params.set('department', f.department)
    if (f.employment_type) params.set('employment_type', f.employment_type)

    const qs = params.toString() ? `?${params}` : ''

    api.get<Employee[]>(`/employees${qs}`)
      .then((d) => { if (id === reqId.current) setEmployees(d) })
      .catch((e) => { if (id === reqId.current) setError(e instanceof Error ? e.message : 'Failed to load employees') })
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [])

  // First load fires immediately; search-driven refetches debounce 300ms so
  // typing doesn't fire a request per keystroke.
  const firstLoad = useRef(true)
  const prevSearch = useRef(filters.search)
  useEffect(() => {
    const searchChanged = filters.search !== prevSearch.current
    prevSearch.current = filters.search
    if (firstLoad.current || !searchChanged) {
      firstLoad.current = false
      fetchEmployees()
      return
    }
    const t = setTimeout(fetchEmployees, 300)
    return () => clearTimeout(t)
  }, [fetchEmployees, filters.status, filters.search, filters.department, filters.employment_type])

  const refetch = useCallback(() => {
    fetchEmployees()
    api.get<string[]>('/employees/departments').then(setDepartments).catch(() => {})
    api.get<Record<string, OnboardingProgress>>('/employees/onboarding-progress')
      .then(setOnboardingProgress).catch(() => {})
  }, [fetchEmployees])

  return { employees, departments, onboardingProgress, loading, error, refetch }
}
