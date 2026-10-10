import SwiftUI

/// A manager's write the server refused with a 409 they may override, waiting
/// for their answer. Yes runs the same write again with force.
struct ForcePrompt: Identifiable {
    let id = UUID()
    let conflict: ScheduleConflict
    /// The schedule editor sends a meal-break advisory to the shift's break
    /// instead of offering to force it (the web editor's rule).
    let refusesMealBreak: Bool
    let retry: () async throws -> Void

    var forceable: Bool { !(refusesMealBreak && conflict.isMealBreak) }

    /// Runs `write(false)`. A conflict a manager may override becomes a prompt
    /// whose yes runs `write(true)`; any other failure is thrown.
    @MainActor
    static func run(
        _ prompt: Binding<ForcePrompt?>,
        refusesMealBreak: Bool = false,
        _ write: @escaping (_ force: Bool) async throws -> Void
    ) async throws {
        do {
            try await write(false)
        } catch APIError.scheduleConflict(let conflict) {
            prompt.wrappedValue = ForcePrompt(conflict: conflict, refusesMealBreak: refusesMealBreak) {
                try await write(true)
            }
        }
    }
}

extension View {
    /// The "Schedule anyway?" confirmation. `onError` hears about a forced
    /// retry that still failed.
    func forcePrompt(_ prompt: Binding<ForcePrompt?>, onError: @escaping (String) -> Void) -> some View {
        let shown = Binding(get: { prompt.wrappedValue != nil }, set: { if !$0 { prompt.wrappedValue = nil } })
        let current = prompt.wrappedValue
        return alert(
            current?.forceable == false ? "Set a break first" : "Schedule anyway?",
            isPresented: shown,
            presenting: current
        ) { item in
            if item.forceable {
                Button("Schedule anyway") {
                    Task {
                        do { try await item.retry() } catch { onError(error.localizedDescription) }
                    }
                }
                Button("Cancel", role: .cancel) {}
            } else {
                Button("OK", role: .cancel) {}
            }
        } message: { item in
            Text(item.forceable
                 ? item.conflict.prompt
                 : item.conflict.prompt + "\n\nEdit the shift's break, then try again.")
        }
    }
}
