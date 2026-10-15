import XCTest
@testable import Matcha

/// Every Espresso feature ships with a how-it-works guide that covers both how
/// to use it and what to expect, and each person sees each guide on its own
/// only once. No network, no signed-in session.
@MainActor
final class FeatureGuideTests: XCTestCase {

    func testEveryFeatureHasAGuide() {
        XCTAssertEqual(FeatureGuide.all.count, FeatureGuideID.allCases.count,
                       "one guide per feature, no duplicates")
        for id in FeatureGuideID.allCases {
            let guide = FeatureGuide.guide(for: id)
            XCTAssertEqual(guide.id, id)
            XCTAssertFalse(guide.name.isEmpty, "\(id) has no name")
            XCTAssertTrue((3...6).contains(guide.pages.count),
                          "\(id) has \(guide.pages.count) pages; keep it to 3–6")
        }
    }

    func testEveryGuideSaysHowToUseItAndWhatToExpect() {
        for guide in FeatureGuide.all {
            XCTAssertTrue(guide.pages.contains { $0.stage == .howTo },
                          "\(guide.id) never says how to use it")
            XCTAssertTrue(guide.pages.contains { $0.stage == .expect },
                          "\(guide.id) never says what to expect")
            for page in guide.pages {
                XCTAssertFalse(page.title.isEmpty, "\(guide.id) has a page with no title")
                XCTAssertFalse(page.body.isEmpty && page.points.isEmpty,
                               "\(guide.id) page “\(page.title)” is empty")
                XCTAssertFalse(page.icon.isEmpty, "\(guide.id) page “\(page.title)” has no icon")
            }
        }
    }

    func testEverySidebarSectionHasItsOwnGuideUnderTheSameName() {
        let guides = SidebarSectionOrderStore.Section.allCases.map(\.guide)
        XCTAssertEqual(Set(guides).count, guides.count, "two sections share a guide")
        for section in SidebarSectionOrderStore.Section.allCases {
            XCTAssertEqual(FeatureGuide.guide(for: section.guide).name, section.displayName,
                           "the guide for \(section) should use the sidebar's name")
        }
    }

    func testSeenIsPerPersonAndPerGuide() {
        let defaults = UserDefaults(suiteName: "FeatureGuideTests-\(UUID().uuidString)")!
        XCTAssertFalse(FeatureGuideSeen.isSeen(.jobSearch, userId: "u1", defaults: defaults))
        FeatureGuideSeen.markSeen(.jobSearch, userId: "u1", defaults: defaults)
        XCTAssertTrue(FeatureGuideSeen.isSeen(.jobSearch, userId: "u1", defaults: defaults))
        XCTAssertFalse(FeatureGuideSeen.isSeen(.jobSearch, userId: "u2", defaults: defaults),
                       "another account on this Mac still gets the guide")
        XCTAssertFalse(FeatureGuideSeen.isSeen(.calendar, userId: "u1", defaults: defaults))
    }

    func testTheOldReviewHowToStillCountsAsSeen() {
        let defaults = UserDefaults(suiteName: "FeatureGuideTests-\(UUID().uuidString)")!
        defaults.set(true, forKey: "werk-review-wizard-seen")
        XCTAssertTrue(FeatureGuideSeen.isSeen(.reviewBoard, userId: "u1", defaults: defaults))
        XCTAssertFalse(FeatureGuideSeen.isSeen(.jobSearch, userId: "u1", defaults: defaults))
    }
}
