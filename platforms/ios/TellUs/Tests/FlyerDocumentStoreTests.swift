import XCTest
@testable import TellUs

@MainActor
final class FlyerDocumentStoreTests: XCTestCase {
    func testNoOpApplyDoesNotDirtyDocument() {
        let initial = FlyerDesignFactory.blank()
        let store = FlyerDocumentStore(initial)

        store.apply(initial, commit: true)

        XCTAssertFalse(store.isDirty)
        XCTAssertFalse(store.canUndo)
    }

    func testUncommittedGestureThenCommitCreatesOneUndoStep() {
        let initial = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.text(in: initial, text: "Headline")
        var first = initial
        first.layers = [layer]
        let store = FlyerDocumentStore(first)

        for x in stride(from: 10.0, through: 40.0, by: 1.0) {
            store.apply(first.replacingLayer(layer.moved(to: CGPoint(x: x, y: 10))), commit: false)
        }
        let final = store.design
        store.apply(final, commit: true)

        XCTAssertTrue(store.canUndo)
        store.undo()
        XCTAssertEqual(store.design, first)
        XCTAssertFalse(store.canUndo)
        XCTAssertTrue(store.canRedo)
    }

    func testRedoRestoresCommittedDocumentAndNewEditClearsRedo() {
        let initial = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.text(in: initial, text: "A")
        var first = initial
        first.layers = [layer]
        let second = first.replacingLayer(layer.replacing(y: 200))
        let third = second.replacingLayer(layer.replacing(y: 300))
        let store = FlyerDocumentStore(first)

        store.apply(second, commit: true)
        store.apply(third, commit: true)
        store.undo()
        XCTAssertEqual(store.design, second)
        store.redo()
        XCTAssertEqual(store.design, third)
        store.undo()
        store.apply(first, commit: true)
        XCTAssertFalse(store.canRedo)
    }

    func testSaveOnlyClearsDirtyForCurrentRevision() {
        let initial = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.text(in: initial, text: "A")
        var edited = initial
        edited.layers = [layer]
        let store = FlyerDocumentStore(initial)

        store.apply(edited, commit: true)
        let oldSnapshot = store.snapshotForSave()
        store.apply(edited.replacingLayer(layer.replacing(y: 100)), commit: true)
        store.markSaved(oldSnapshot)
        XCTAssertTrue(store.isDirty)

        let current = store.snapshotForSave()
        store.markSaved(current)
        XCTAssertFalse(store.isDirty)
    }

    func testHistoryCapsAtFiftyEntries() {
        let initial = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.text(in: initial, text: "A")
        let store = FlyerDocumentStore(initial)

        var design = initial
        for index in 0..<60 {
            let current = layer.replacing(y: Double(index))
            design = design.replacingLayer(current)
            if design.layers.isEmpty { design.layers = [current] }
            store.apply(design, commit: true)
        }

        var undoCount = 0
        while store.canUndo {
            store.undo()
            undoCount += 1
        }
        XCTAssertEqual(undoCount, 50)
    }
}
