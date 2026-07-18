import { Loader2 } from 'lucide-react'
import SurfaceShell from '../../components/SurfaceShell'
import StaffImportModal from '../../components/StaffImportModal'
import { useBookings } from './Bookings/useBookings'
import { LocationSwitcher } from './Bookings/LocationSwitcher'
import { PendingRequests } from './Bookings/PendingRequests'
import { ScheduleSection } from './Bookings/ScheduleSection'
import { StaffSection } from './Bookings/StaffSection'
import { BookingTypesSection } from './Bookings/BookingTypesSection'
import { AvailabilitySection } from './Bookings/AvailabilitySection'
import { RateRulesSection } from './Bookings/RateRulesSection'
import { DiscountsSection } from './Bookings/DiscountsSection'
import { RiderSection } from './Bookings/RiderSection'

export default function Bookings() {
  const b = useBookings()

  if (b.loading) {
    return <SurfaceShell title="Bookings"><div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div></SurfaceShell>
  }

  return (
    <SurfaceShell title="Bookings" subtitle="Appointment types, availability, pricing, and requests.">
      {b.error && <p className="mb-4 text-sm text-red-400">{b.error}</p>}

      {/* Location switcher — manage each location's appts/staff/hours separately.
          Multi-location sites only; single-location sites keep a simpler page. */}
      {b.multiLoc && (
        <LocationSwitcher
          locations={b.locations}
          selLoc={b.selLoc}
          switchLocation={b.switchLocation}
          showLocMgr={b.showLocMgr}
          setShowLocMgr={b.setShowLocMgr}
          locForm={b.locForm}
          setLocForm={b.setLocForm}
          addLocation={b.addLocation}
          setLocationDefault={b.setLocationDefault}
          deactivateLocation={b.deactivateLocation}
        />
      )}

      {/* Requests needing approval — the creator's queue */}
      {b.pending.length > 0 && (
        <PendingRequests pending={b.pending} acceptBooking={b.acceptBooking} declineBooking={b.declineBooking} />
      )}

      {/* Schedule — calendar / list of all bookings */}
      <ScheduleSection
        view={b.view}
        setView={b.setView}
        bookings={b.bookings}
        slots={b.slots}
        types={b.types}
        acceptBooking={b.acceptBooking}
        declineBooking={b.declineBooking}
        setBookingStatus={b.setBookingStatus}
      />

      {/* Staff / stylists */}
      <StaffSection
        siteId={b.siteId}
        multiLoc={b.multiLoc}
        staff={b.staff}
        staffForm={b.staffForm}
        setStaffForm={b.setStaffForm}
        addStaff={b.addStaff}
        removeStaff={b.removeStaff}
        setShowStaffImport={b.setShowStaffImport}
      />

      {b.showStaffImport && (
        <StaffImportModal
          siteId={b.siteId || ''}
          locations={b.locations}
          multiBranch={b.multiLoc}
          onClose={() => b.setShowStaffImport(false)}
          onImported={() => { b.loadConfig(b.locations, b.selLoc).catch(() => {}) }}
        />
      )}

      {/* Booking types */}
      <BookingTypesSection
        types={b.types}
        typeForm={b.typeForm}
        setTypeForm={b.setTypeForm}
        addType={b.addType}
        staff={b.staff}
        patchType={b.patchType}
        removeType={b.removeType}
        toggleTypeStaff={b.toggleTypeStaff}
      />

      {/* Availability */}
      <AvailabilitySection
        slots={b.slots}
        setSlots={b.setSlots}
        setSlot={b.setSlot}
        types={b.types}
        staff={b.staff}
        addSlot={b.addSlot}
        saveAvailability={b.saveAvailability}
        savingAvail={b.savingAvail}
      />

      {/* Rate rules — dynamic time pricing (for hourly types) */}
      <RateRulesSection
        rules={b.rules}
        setRules={b.setRules}
        setRule={b.setRule}
        types={b.types}
        hasHourly={b.hasHourly}
        addRule={b.addRule}
        saveRules={b.saveRules}
        savingRules={b.savingRules}
      />

      {/* Discounts — promotional markdowns */}
      <DiscountsSection
        discounts={b.discounts}
        setDiscounts={b.setDiscounts}
        setDiscount={b.setDiscount}
        types={b.types}
        products={b.products}
        addDiscount={b.addDiscount}
        saveDiscounts={b.saveDiscounts}
        savingDiscounts={b.savingDiscounts}
      />

      {/* Rider — Pro creators only */}
      {b.isCreator && (
        <RiderSection
          riderUnlocked={b.riderUnlocked}
          rider={b.rider}
          setRider={b.setRider}
          setRiderItem={b.setRiderItem}
          addRiderItem={b.addRiderItem}
          saveRider={b.saveRider}
          savingRider={b.savingRider}
        />
      )}

    </SurfaceShell>
  )
}
