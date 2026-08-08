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

    @MainActor
    func testNoMatchesFalseWhenSearchErrorSet() {
        let vm = PlacesViewModel()
        vm.query = "jo"
        vm.searching = false
        vm.searchError = "Search failed — try again."
        XCTAssertFalse(vm.noMatches)
    }

    @MainActor
    func testQueryChangedSyncSetsSearching() {
        // Regression: `searching` must flip true synchronously on keystroke,
        // not only after the 450ms debounce fires — otherwise `noMatches`
        // flashes true (and the manual-add form with it) for every keystroke.
        let vm = PlacesViewModel()
        vm.query = "jo"
        XCTAssertTrue(vm.searching)
        XCTAssertFalse(vm.noMatches)
    }

    @MainActor
    func testQueryChangedResetsManualFallbackState() {
        let vm = PlacesViewModel()
        vm.showManualForm = true
        vm.manualError = "stale error"
        vm.query = "jo"
        XCTAssertFalse(vm.showManualForm)
        XCTAssertNil(vm.manualError)
    }

    func testQueryStringEncodesPlusAsPercent2B() {
        // Starlette's parse_qsl decodes literal "+" as a space; without
        // force-encoding, "C++ Cafe" would search "%C   Cafe%" server-side.
        let qs = PlacesService.queryString([URLQueryItem(name: "q", value: "C++ Cafe")])
        XCTAssertEqual(qs, "?q=C%2B%2B%20Cafe")
    }
}
