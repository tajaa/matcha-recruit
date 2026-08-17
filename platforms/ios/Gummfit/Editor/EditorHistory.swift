import Foundation

struct EditorSnapshot: Equatable {
    var blocks: [CappeBlock]
    var title: String
    var status: CappePageStatus
    var theme: [String: JSONValue]
    var meta: [String: JSONValue]
}

@MainActor
final class EditorHistory {
    private var undoStack: [EditorSnapshot]
    private var redoStack: [EditorSnapshot] = []
    private var lastRecordAt: Date?
    private let limit: Int
    private let coalesceWindow: TimeInterval

    init(initial: EditorSnapshot, limit: Int = 60, coalesceWindow: TimeInterval = 0.6) {
        self.undoStack = [initial]
        self.limit = max(1, limit)
        self.coalesceWindow = max(0, coalesceWindow)
    }

    var canUndo: Bool { undoStack.count > 1 }
    var canRedo: Bool { !redoStack.isEmpty }

    func record(_ snapshot: EditorSnapshot, coalescing: Bool) {
        let now = Date()
        if coalescing,
           let lastRecordAt,
           now.timeIntervalSince(lastRecordAt) <= coalesceWindow,
           undoStack.count > 1 {
            undoStack[undoStack.count - 1] = snapshot
        } else {
            undoStack.append(snapshot)
            if undoStack.count > limit + 1 {
                undoStack.removeFirst()
            }
        }
        redoStack.removeAll(keepingCapacity: true)
        lastRecordAt = now
    }

    func checkpoint() {
        lastRecordAt = nil
    }

    func undo() -> EditorSnapshot? {
        guard undoStack.count > 1 else { return nil }
        redoStack.append(undoStack.removeLast())
        lastRecordAt = nil
        return undoStack.last
    }

    func redo() -> EditorSnapshot? {
        guard let snapshot = redoStack.popLast() else { return nil }
        undoStack.append(snapshot)
        lastRecordAt = nil
        return snapshot
    }
}
