import SwiftUI

/// A manager's write the server refused with a 409 they may override, waiting
/// for their answer. Yes runs the same write again with force.
struct ForcePrompt: Identifiable {
    enum Choice { case force, fixBreak }

    let id = UUID()
    let conflict: ScheduleConflict
    /// For a meal-break advisory: give the shift the break the law requires,
    /// then carry on. The web editor sends that advisory to the shift's break
    /// rather than forcing past it; without a fix the prompt forces as usual.
    let fixBreak: (() async throws -> Void)?
    let retry: () async throws -> Void

    var choice: Choice { conflict.isMealBreak && fixBreak != nil ? .fixBreak : .force }

    /// Runs `write(false)`. A conflict a manager may override becomes a prompt
    /// whose yes runs `write(true)`; any other failure is thrown.
    @MainActor
    static func run(
        _ prompt: Binding<ForcePrompt?>,
        fixBreak: (() async throws -> Void)? = nil,
        _ write: @escaping (_ force: Bool) async throws -> Void
    ) async throws {
        do {
            try await write(false)
        } catch APIError.scheduleConflict(let conflict) {
            // The manager has read every advisory in the prompt; once the
            // break is fixed the rest go through as they agreed.
            let fix = fixBreak.map { fix in { try await fix(); try await write(true) } }
            prompt.wrappedValue = ForcePrompt(conflict: conflict, fixBreak: fix) { try await write(true) }
        }
    }
}

extension View {
    /// The "Schedule anyway?" confirmation. `onError` hears about a retry that
    /// still failed.
    func forcePrompt(_ prompt: Binding<ForcePrompt?>, onError: @escaping (String) -> Void) -> some View {
        let shown = Binding(get: { prompt.wrappedValue != nil }, set: { if !$0 { prompt.wrappedValue = nil } })
        let current = prompt.wrappedValue
        return alert(
            current?.choice == .fixBreak ? "This shift needs a meal break" : "Schedule anyway?",
            isPresented: shown,
            presenting: current
        ) { item in
            switch item.choice {
            case .fixBreak:
                Button("Add the required break") { run(item.fixBreak, onError) }
            case .force:
                Button("Schedule anyway") { run(item.retry, onError) }
            }
            Button("Cancel", role: .cancel) {}
        } message: { item in
            Text(item.choice == .fixBreak
                 ? item.conflict.prompt + "\n\nMatcha can set the break the law requires on this shift, then continue."
                 : item.conflict.prompt)
        }
    }
}

private func run(_ action: (() async throws -> Void)?, _ onError: @escaping (String) -> Void) {
    guard let action else { return }
    Task {
        do { try await action() } catch { onError(error.localizedDescription) }
    }
}
