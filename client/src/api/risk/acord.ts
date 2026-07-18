import { api } from '../client'

export type AcordForm = { form: string; label: string }

export function listAcordForms() {
  return api.get<{ forms: AcordForm[] }>('/acord/forms')
}
export function downloadAcord(form: string) {
  return api.download(`/acord/${form}.pdf`, `acord-${form}.pdf`)
}
