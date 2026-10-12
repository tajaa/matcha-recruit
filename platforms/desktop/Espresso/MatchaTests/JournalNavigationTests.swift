import XCTest
@testable import Matcha

final class JournalNavigationTests: XCTestCase {
    private func folder(_ id: String, _ name: String, parent: String? = nil) -> MWJournalFolder {
        MWJournalFolder(id: id, name: name, parentId: parent, createdBy: nil, createdAt: nil, color: nil)
    }

    func testNestedFoldersStayWithTheirParentAndSortByName() {
        let folders = [folder("z", "Work"), folder("b", "ideas", parent: "a"),
                       folder("c", "Ideas", parent: "a"), folder("a", "Personal"),
                       folder("d", "Drafts", parent: "b")]
        let rows = JournalFolderTree.visible(folders, collapsed: [])
        XCTAssertEqual(rows.map { $0.folder.id }, ["a", "b", "d", "c", "z"])
        XCTAssertEqual(rows.map(\.depth), [0, 1, 2, 1, 0])
    }

    func testCollapsingAFolderHidesOnlyItsDescendants() {
        let folders = [folder("a", "Personal"), folder("b", "Ideas", parent: "a"),
                       folder("c", "Drafts", parent: "b"), folder("z", "Work")]
        let childCollapsed = JournalFolderTree.visible(folders, collapsed: ["b"])
        XCTAssertEqual(childCollapsed.map { $0.folder.id }, ["a", "b", "z"])
        let rootCollapsed = JournalFolderTree.visible(folders, collapsed: ["a"])
        XCTAssertEqual(rootCollapsed.map { $0.folder.id }, ["a", "z"])
        XCTAssertEqual(JournalFolderTree.visible(folders, collapsed: []).count, 4)
    }

    func testFoldersWithAMissingParentRemainReachable() {
        let rows = JournalFolderTree.visible([folder("a", "Moved", parent: "deleted"),
                                              folder("b", "Child", parent: "a")], collapsed: [])
        XCTAssertEqual(rows.map { $0.folder.id }, ["a", "b"])
        XCTAssertEqual(rows.map(\.depth), [0, 1])
    }

    func testRefreshingFoldersResetsDeletedSelectionAndPreservesOtherFilters() {
        let folders = [folder("a", "Personal")]
        XCTAssertEqual(JournalFolderSelection.folder("removed").validated(in: folders), .all)
        XCTAssertEqual(JournalFolderSelection.folder("a").validated(in: folders), .folder("a"))
        for selection: JournalFolderSelection in [.all, .starred, .shared, .uncategorized] {
            XCTAssertEqual(selection.validated(in: []), selection)
        }
    }
}
