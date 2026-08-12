import type { CappeAvailabilitySlot, CappeBookingType } from '../types'

export function slotAppliesToType(slot: CappeAvailabilitySlot, type: CappeBookingType): boolean {
  if (slot.booking_type_id !== null && slot.booking_type_id !== type.id) return false

  if ((type.staff_ids || []).length === 0) return slot.staff_id == null

  return slot.staff_id == null || type.staff_ids.includes(slot.staff_id)
}

export function applicableSlotsForType(
  slots: CappeAvailabilitySlot[],
  type: CappeBookingType,
): CappeAvailabilitySlot[] {
  return slots.filter((slot) => slotAppliesToType(slot, type))
}

export function unavailableStaffWindowIndexes(
  slots: CappeAvailabilitySlot[],
  types: CappeBookingType[],
): Set<number> {
  const activeTypes = types.filter((type) => type.status === 'active')
  return new Set(slots.flatMap((slot, index) => (
    slot.staff_id != null && !activeTypes.some((type) => slotAppliesToType(slot, type)) ? [index] : []
  )))
}
