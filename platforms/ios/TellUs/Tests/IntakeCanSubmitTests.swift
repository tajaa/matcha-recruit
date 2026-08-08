import XCTest
@testable import TellUs

@MainActor
final class IntakeCanSubmitTests: XCTestCase {
    private func makeVM() -> IntakeViewModel { IntakeViewModel(token: "test-token") }

    func testRequiresRatingWhenPosting() {
        let vm = makeVM()
        vm.description = "Great service"
        vm.postAsReview = true
        vm.rating = 0
        XCTAssertFalse(vm.canSubmit)
    }

    func testRatingSatisfies() {
        let vm = makeVM()
        vm.description = "Great service"
        vm.postAsReview = true
        vm.rating = 4
        XCTAssertTrue(vm.canSubmit)
    }

    func testOptOutSkipsRating() {
        let vm = makeVM()
        vm.description = "Great service"
        vm.postAsReview = false
        vm.rating = 0
        XCTAssertTrue(vm.canSubmit)
    }

    func testEmptyDescriptionBlocks() {
        let vm = makeVM()
        vm.description = ""
        vm.postAsReview = false
        XCTAssertFalse(vm.canSubmit)
    }
}
