import Foundation

/// Replaces the ~12 copy-pasted `isLoading = true; defer {...}; do {...} catch
/// { if error.isCancellation { return }; self.error = ... }` blocks scattered
/// across the VMs. Conforming types just call `withLoad { ... }`.
@MainActor
protocol LoadableVM: AnyObject {
    var isLoading: Bool { get set }
    var error: String? { get set }
}

enum LoadOutcome: Equatable { case success, cancelled, failed }

extension LoadableVM {
    /// Cancellation is reported, not swallowed. A caller that tracks its own
    /// per-dataset state needs to tell "loaded, genuinely empty" apart from
    /// "cancelled, data never arrived" — the latter must stay retryable.
    @discardableResult
    func withLoad(_ body: () async throws -> Void) async -> LoadOutcome {
        isLoading = true
        defer { isLoading = false }
        do {
            try await body()
            error = nil
            return .success
        } catch {
            if error.isCancellation { return .cancelled }
            self.error = error.localizedDescription
            return .failed
        }
    }
}
