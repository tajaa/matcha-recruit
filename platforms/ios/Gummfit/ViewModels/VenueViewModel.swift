import Foundation
import Observation

@MainActor
@Observable
final class VenueViewModel: LoadableVM {
    var locations: [CappeLocation] = []
    var staff: [CappeStaff] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            async let locations = VenueService.shared.listLocations(siteId: siteId)
            async let staff = VenueService.shared.listStaff(siteId: siteId)
            (self.locations, self.staff) = try await (locations, staff)
        }
    }

    func createLocation(siteId: String, _ body: CappeLocationCreate) async {
        do {
            locations.append(try await VenueService.shared.createLocation(siteId: siteId, body))
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func updateLocation(siteId: String, locationId: String, _ body: CappeLocationUpdate) async {
        do {
            let updated = try await VenueService.shared.updateLocation(siteId: siteId, locationId: locationId, body)
            if let idx = locations.firstIndex(where: { $0.id == locationId }) { locations[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func deleteLocation(siteId: String, locationId: String) async {
        do {
            try await VenueService.shared.deleteLocation(siteId: siteId, locationId: locationId)
            locations.removeAll { $0.id == locationId }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func createStaff(siteId: String, _ body: CappeStaffCreate) async {
        do {
            staff.append(try await VenueService.shared.createStaff(siteId: siteId, body))
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func updateStaff(siteId: String, staffId: String, _ body: CappeStaffUpdate) async {
        do {
            let updated = try await VenueService.shared.updateStaff(siteId: siteId, staffId: staffId, body)
            if let idx = staff.firstIndex(where: { $0.id == staffId }) { staff[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func deleteStaff(siteId: String, staffId: String) async {
        do {
            try await VenueService.shared.deleteStaff(siteId: siteId, staffId: staffId)
            staff.removeAll { $0.id == staffId }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
