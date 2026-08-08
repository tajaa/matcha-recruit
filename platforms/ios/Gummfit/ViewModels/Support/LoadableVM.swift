import Foundation

/// Replaces the ~12 copy-pasted `isLoading = true; defer {...}; do {...} catch
/// { if error.isCancellation { return }; self.error = ... }` blocks scattered
/// across the VMs. Conforming types just call `withLoad { ... }`.
@MainActor
protocol LoadableVM: AnyObject {
    var isLoading: Bool { get set }
    var error: String? { get set }
}

extension LoadableVM {
    func withLoad(_ body: () async throws -> Void) async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await body()
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
