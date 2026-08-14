import Foundation
import Observation

struct FlyerSaveSnapshot: Equatable {
    let design: FlyerDesign
    let revision: UInt64
}

/// Pure document state for the editor. Gesture updates can stream through
/// `apply(_:commit: false)` without turning one drag into dozens of undo steps.
@MainActor
@Observable
final class FlyerDocumentStore {
    private(set) var design: FlyerDesign
    private(set) var isDirty = false
    private(set) var canUndo = false
    private(set) var canRedo = false
    private(set) var revision: UInt64 = 0

    private var baseline: FlyerDesign
    private var past: [FlyerDesign] = []
    private var future: [FlyerDesign] = []

    private static let maxHistory = 50

    init(_ initial: FlyerDesign) {
        design = initial
        baseline = initial
    }

    func reset(to next: FlyerDesign) {
        design = next
        baseline = next
        past = []
        future = []
        isDirty = false
        revision &+= 1
        updateAvailability()
    }

    func apply(_ next: FlyerDesign, commit: Bool) {
        design = next
        revision &+= 1
        isDirty = true
        guard commit else { return }
        if baseline != next {
            past.append(baseline)
            if past.count > Self.maxHistory { past.removeFirst(past.count - Self.maxHistory) }
        }
        baseline = next
        future = []
        updateAvailability()
    }

    func undo() {
        guard let previous = past.popLast() else { return }
        future.insert(baseline, at: 0)
        if future.count > Self.maxHistory { future.removeLast(future.count - Self.maxHistory) }
        design = previous
        baseline = previous
        isDirty = true
        revision &+= 1
        updateAvailability()
    }

    func redo() {
        guard !future.isEmpty else { return }
        let next = future.removeFirst()
        past.append(baseline)
        if past.count > Self.maxHistory { past.removeFirst(past.count - Self.maxHistory) }
        design = next
        baseline = next
        isDirty = true
        revision &+= 1
        updateAvailability()
    }

    func snapshotForSave() -> FlyerSaveSnapshot {
        FlyerSaveSnapshot(design: design, revision: revision)
    }

    /// A save may clear dirty state only when the document has not changed
    /// since its snapshot was captured.
    func markSaved(_ snapshot: FlyerSaveSnapshot) {
        guard snapshot.revision == revision, snapshot.design == design else { return }
        isDirty = false
    }

    private func updateAvailability() {
        canUndo = !past.isEmpty
        canRedo = !future.isEmpty
    }
}
