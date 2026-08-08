import Foundation
import Observation

@MainActor
@Observable
final class ClientsViewModel: LoadableVM {
    var clients: [CappeClient] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.clients = try await ClientsService.shared.list(siteId: siteId)
        }
    }

    func upsert(siteId: String, _ body: CappeClientCreate) async {
        do {
            let saved = try await ClientsService.shared.upsert(siteId: siteId, body)
            if let idx = clients.firstIndex(where: { $0.email == saved.email }) {
                clients[idx] = saved
            } else {
                clients.insert(saved, at: 0)
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func delete(siteId: String, email: String) async {
        do {
            try await ClientsService.shared.delete(siteId: siteId, email: email)
            clients.removeAll { $0.email == email }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
