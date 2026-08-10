import Foundation
import Observation

enum InboxScope: Hashable {
    case consumer
    case business(brandID: String?)
}

@MainActor
@Observable
final class DmThreadsViewModel: LoadableVM {
    let scope: InboxScope
    var threads: [DmThread] = []
    var isLoading = false
    var error: String?
    var isPolling = false
    private var pollingTask: Task<Void, Never>?

    init(scope: InboxScope = .consumer) {
        self.scope = scope
    }

    func load() async {
        await withLoad {
            let brandID: String?
            switch scope {
            case .consumer: brandID = nil
            case .business(let value): brandID = value
            }
            threads = try await DmService.shared.threads(brandID: brandID)
        }
    }

    func startPolling() {
        guard pollingTask == nil else { return }
        isPolling = true
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(15))
                guard !Task.isCancelled, let self else { return }
                await self.load()
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
        isPolling = false
    }

    deinit { pollingTask?.cancel() }
}
