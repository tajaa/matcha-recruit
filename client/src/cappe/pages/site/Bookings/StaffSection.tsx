import type { Dispatch, SetStateAction } from 'react'
import { Plus, Trash2, Users, Upload } from 'lucide-react'
import ImageUpload from '../../../components/ImageUpload'
import type { CappeStaff } from '../../../types'
import { inputCls } from './constants'
import type { StaffForm } from './types'

interface StaffSectionProps {
  siteId: string | undefined
  multiLoc: boolean
  staff: CappeStaff[]
  staffForm: StaffForm
  setStaffForm: Dispatch<SetStateAction<StaffForm>>
  addStaff: (e: React.FormEvent) => void
  removeStaff: (id: string) => void
  setShowStaffImport: Dispatch<SetStateAction<boolean>>
}

export function StaffSection({
  siteId, multiLoc, staff, staffForm, setStaffForm, addStaff, removeStaff, setShowStaffImport,
}: StaffSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-zinc-100"><Users className="h-4 w-4 text-emerald-400" /> Staff</h2>
        <button onClick={() => setShowStaffImport(true)} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800">
          <Upload className="h-3.5 w-3.5" /> Import CSV
        </button>
      </div>
      <p className="mb-3 mt-1 text-xs text-zinc-500">Add the people customers book with. Then choose who performs each service below — customers can pick a specific person or “any available”. Leave a service with no staff to keep one shared calendar.{multiLoc && ' Importing a CSV with a branch column maps each employee to the right location automatically.'}</p>
      <form onSubmit={addStaff} className="mb-4 flex flex-wrap items-end gap-2">
        <input value={staffForm.name} onChange={(e) => setStaffForm({ ...staffForm, name: e.target.value })} placeholder="Name — e.g. Maria" className={`w-44 ${inputCls}`} />
        <input value={staffForm.bio} onChange={(e) => setStaffForm({ ...staffForm, bio: e.target.value })} placeholder="Title / bio (optional)" className={`flex-1 ${inputCls}`} />
        <div className="w-56"><ImageUpload siteId={siteId || ''} value={staffForm.image_url} onChange={(url) => setStaffForm({ ...staffForm, image_url: url })} placeholder="Photo (optional)" /></div>
        <button type="submit" className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"><Plus className="h-4 w-4" /> Add</button>
      </form>
      {staff.length === 0 ? (
        <p className="text-sm text-zinc-400">No staff yet — your bookings use one shared calendar.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {staff.map((s) => (
            <li key={s.id} className="flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-950 py-1 pl-1 pr-3 text-sm">
              <span className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-full bg-zinc-800 text-xs font-semibold uppercase text-zinc-300">
                {s.image_url ? <img src={s.image_url} alt="" className="h-full w-full object-cover" /> : (s.name || '?').slice(0, 1)}
              </span>
              <span className="text-zinc-200">{s.name}</span>
              <button onClick={() => removeStaff(s.id)} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
