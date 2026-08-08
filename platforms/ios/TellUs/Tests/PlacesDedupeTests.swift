import XCTest
@testable import TellUs

final class PlacesDedupeTests: XCTestCase {
    func testSuggestionsDedupedAgainstDbResults() {
        let db = [
            PlaceSearchResult(slug: "a", name: "A", logo_url: nil, city: nil, state: nil,
                               claimed: false, intake_token: "t1", review_count: 0,
                               google_place_id: "ChIJ_A")
        ]
        let suggestions = [
            PlaceSuggestion(place_id: "ChIJ_A", name: "A", secondary_text: nil),
            PlaceSuggestion(place_id: "ChIJ_B", name: "B", secondary_text: nil),
        ]
        let result = PlacesViewModel.dedupe(suggestions, against: db)
        XCTAssertEqual(result.map(\.place_id), ["ChIJ_B"])
    }

    func testSuggestionsUnfilteredWhenNoOverlap() {
        let db = [
            PlaceSearchResult(slug: "a", name: "A", logo_url: nil, city: nil, state: nil,
                               claimed: false, intake_token: "t1", review_count: 0,
                               google_place_id: nil)
        ]
        let suggestions = [PlaceSuggestion(place_id: "ChIJ_B", name: "B", secondary_text: nil)]
        let result = PlacesViewModel.dedupe(suggestions, against: db)
        XCTAssertEqual(result.map(\.place_id), ["ChIJ_B"])
    }

    @MainActor
    func testNoMatchesRequiresTwoChars() {
        let vm = PlacesViewModel()
        vm.query = "j"
        XCTAssertFalse(vm.noMatches)
    }

    @MainActor
    func testNoMatchesFalseWhileSearching() {
        let vm = PlacesViewModel()
        vm.query = "jo"
        vm.searching = true
        XCTAssertFalse(vm.noMatches)
    }
}
