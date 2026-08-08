import Foundation
import Observation

@MainActor
@Observable
final class BookingTypesViewModel: LoadableVM {
    var types: [CappeBookingType] = []
    var isLoading = false
    var error: String?

    func load(siteId: String, locationId: String? = nil) async {
        await withLoad {
            self.types = try await BookingsService.shared.listTypes(siteId: siteId, locationId: locationId)
        }
    }

    func create(siteId: String, _ body: CappeBookingTypeCreate) async {
        do {
            let created = try await BookingsService.shared.createType(siteId: siteId, body)
            types.insert(created, at: 0)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func update(siteId: String, typeId: String, _ body: CappeBookingTypeUpdate) async {
        do {
            let updated = try await BookingsService.shared.updateType(siteId: siteId, typeId: typeId, body)
            if let idx = types.firstIndex(where: { $0.id == typeId }) { types[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func delete(siteId: String, typeId: String) async {
        do {
            try await BookingsService.shared.deleteType(siteId: siteId, typeId: typeId)
            types.removeAll { $0.id == typeId }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
