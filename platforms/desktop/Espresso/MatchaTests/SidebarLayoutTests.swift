import XCTest
@testable import Matcha

/// The sidebar: groups and their saved order, the one Pinned list, the
/// Espresso card's line. No network, no signed-in session.
@MainActor
final class SidebarLayoutTests: XCTestCase {
    typealias Store = SidebarSectionOrderStore

    func testSectionsSitInTheirGroups() {
        XCTAssertEqual(Store.Group.work.sections, [.projects, .channels, .threads])
        XCTAssertEqual(Store.Group.personal.sections, [.calendar, .productivity, .journals, .email])
        XCTAssertEqual(Store.Group.allCases.map(\.title), ["WORK", "PERSONAL"])
        // Espresso, Tasks and Job search are fixed rows (or gone), not sections.
        for gone in ["assistant", "tasks", "jobs"] { XCTAssertNil(Store.Section(rawValue: gone)) }
        XCTAssertEqual(Set(Store.Group.allCases.flatMap(\.sections)), Set(Store.Section.allCases))
    }

    func testTheOldFlatOrderCarriesOverIntoGroups() {
        let flat = ["email", "assistant", "threads", "jobs", "calendar", "projects", "tasks", "bogus"]
        let orders = Store.orders(fromFlat: flat)
        // Each group keeps the person's relative order, then the rest in the default order.
        XCTAssertEqual(orders[.work], [.threads, .projects, .channels])
        XCTAssertEqual(orders[.personal], [.email, .calendar, .productivity, .journals])
        XCTAssertEqual(Store.orders(fromFlat: [])[.work], Store.Group.work.sections)
    }

    func testASavedGroupOrderIsCompletedAndCleaned() {
        let saved = ["work": ["channels", "channels", "email", "nope"], "personal": ["journals"]]
        let orders = Store.orders(from: saved)
        XCTAssertEqual(orders[.work], [.channels, .projects, .threads])  // email isn't work; no repeats
        XCTAssertEqual(orders[.personal], [.journals, .calendar, .productivity, .email])
        XCTAssertEqual(Store.orders(from: [:])[.personal], Store.Group.personal.sections)
    }

    func testPinnedMergesTabsAndStarsOnce() {
        let tabs = [WorkTab.home,
                    WorkTab(kind: .project, entityId: "p1", title: "Launch"),
                    WorkTab(kind: .channel, entityId: "c1", title: "general")]
        let stars = [SidebarPinnedView.Star(entityId: "p1", name: "Launch (starred)", kind: .project),
                     SidebarPinnedView.Star(entityId: "j1", name: "Diary", kind: .journal),
                     SidebarPinnedView.Star(entityId: "f1", name: "cv.pdf", kind: .file),
                     SidebarPinnedView.Star(entityId: "j1", name: "Diary again", kind: .journal)]
        let rows = SidebarPinnedView.rows(tabs: tabs, stars: stars)
        XCTAssertEqual(rows.map(\.id), ["project:p1", "channel:c1", "journal:j1", "file:f1"])
        XCTAssertEqual(rows.first?.name, "Launch")  // shown as its tab
        XCTAssertNotNil(rows.first?.tab)
        XCTAssertNil(rows.first?.star)
        XCTAssertNotNil(rows[2].star)
        XCTAssertTrue(SidebarPinnedView.rows(tabs: [.home], stars: []).isEmpty)
    }

    func testLetterTiles() {
        XCTAssertEqual(SidebarPinnedView.tileLetter("#general"), "G")
        XCTAssertEqual(SidebarPinnedView.tileLetter("  québec"), "Q")
        XCTAssertEqual(SidebarPinnedView.tileLetter("2026 plan"), "2")
        XCTAssertEqual(SidebarPinnedView.tileLetter("—"), "•")
        let a = SidebarPinnedView.tileColorIndex("project:p1", count: 8)
        XCTAssertEqual(a, SidebarPinnedView.tileColorIndex("project:p1", count: 8))  // stable, not hashValue
        XCTAssertTrue((0..<8).contains(a))
        XCTAssertEqual(SidebarPinnedView.tileColorIndex("x", count: 0), 0)
        let spread = Set((0..<40).map { SidebarPinnedView.tileColorIndex("channel:c\($0)", count: 8) })
        XCTAssertGreaterThan(spread.count, 4)
    }

    func testTheEspressoCardsLine() throws {
        let runs = try JSONDecoder().decode(MWRunQuota.self, from: Data(#"{"limit": 30, "used": 18, "remaining": 12}"#.utf8))
        XCTAssertEqual(ContentView.espressoCardLine(runs, locked: false), "12 requests left today")
        let one = try JSONDecoder().decode(MWRunQuota.self, from: Data(#"{"limit": 30, "used": 29, "remaining": 1}"#.utf8))
        XCTAssertEqual(ContentView.espressoCardLine(one, locked: false), "1 request left today")
        XCTAssertEqual(ContentView.espressoCardLine(nil, locked: false), "Your private assistant")
        XCTAssertEqual(ContentView.espressoCardLine(runs, locked: true), "Your private assistant, on Pro")
    }
}
