// Shape returned by GET /admin/updates. Content itself lives in the
// admin_updates DB table (migration adminupd01) — see server/app/core/routes/admin.py.

export type AdminUpdateTag = 'new' | 'action-needed'

export type AdminUpdate = {
  id: string
  date: string // ISO YYYY-MM-DD
  category: string // product area, e.g. 'Cappe'
  title: string
  summary: string
  whatsNew: string[] // what changed / what you can now do
  howToUse?: string[] | null // user-facing steps in the app (absent for internal fixes)
  setup?: string[] | null // operator prerequisites before it works (optional)
  notes?: string[] | null // plain-language context / why it matters (optional)
  tag?: AdminUpdateTag | null
}
