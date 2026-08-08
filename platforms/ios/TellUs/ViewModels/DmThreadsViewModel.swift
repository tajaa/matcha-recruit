import Foundation
import Observation

@MainActor
@Observable
final class DmThreadsViewModel: LoadableVM {
    var threads: [DmThread] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            threads = try await DmService.shared.threads()
        }
    }
}
