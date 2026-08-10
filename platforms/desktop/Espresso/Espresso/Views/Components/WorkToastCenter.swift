import Foundation
import Observation

@Observable
final class WorkToastCenter {
    static let shared = WorkToastCenter()

    struct Toast: Identifiable, Equatable {
        let id = UUID()
        let projectId: String
        let projectTitle: String
        let message: String
        let systemImage: String
    }

    private(set) var toasts: [Toast] = []
    private var hoveredIds: Set<UUID> = []

    @MainActor func push(_ toast: Toast) {
        toasts.insert(toast, at: 0)
        toasts = Array(toasts.prefix(3))
        let id = toast.id
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(5))
            if !hoveredIds.contains(id) { dismiss(id: id) }
        }
    }

    @MainActor func setHover(_ id: UUID, _ hovering: Bool) {
        if hovering {
            hoveredIds.insert(id)
        } else {
            hoveredIds.remove(id)
            // The five-second task intentionally leaves a hovered toast alone.
            // Once the pointer leaves, schedule the same short grace period the
            // original inline implementation provided so it cannot stick forever.
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                if !hoveredIds.contains(id) { dismiss(id: id) }
            }
        }
    }
    @MainActor func dismiss(id: UUID) { toasts.removeAll { $0.id == id } }
    @MainActor func dismissAll() { toasts.removeAll() }
    private init() {}
}
