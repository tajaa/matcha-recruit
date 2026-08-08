import XCTest
@testable import Gummfit

/// `ProductFormViewModel.canSubmit`/`optionsValid` mirror the server's
/// `min_length=1` on option group/option names (models/shop.py:21,29) — an
/// empty-named row must never reach the whole-product PATCH/POST, since that
/// would 422 the entire save (name/price/photo edits included) over one
/// abandoned "Add option" tap.
@MainActor
final class ProductFormPruningTests: XCTestCase {
    func testEmptyGroupWithNoOptionsIsValid() {
        let vm = ProductFormViewModel()
        vm.name = "Latte"
        vm.optionGroups = [CappeProductOptionGroupInput(name: "")]
        XCTAssertTrue(vm.optionsValid)
        XCTAssertTrue(vm.canSubmit)
    }

    func testAbandonedOptionInsideNamedGroupIsIgnored() {
        let vm = ProductFormViewModel()
        vm.name = "Latte"
        var group = CappeProductOptionGroupInput(name: "Size")
        group.options = [CappeProductOptionInput(name: "", price_delta_cents: 0)]
        vm.optionGroups = [group]
        XCTAssertTrue(vm.optionsValid)
    }

    func testNamedOptionUnderUnnamedGroupBlocksSubmit() {
        let vm = ProductFormViewModel()
        vm.name = "Latte"
        var group = CappeProductOptionGroupInput(name: "")
        group.options = [CappeProductOptionInput(name: "Large", price_delta_cents: 100)]
        vm.optionGroups = [group]
        XCTAssertFalse(vm.optionsValid)
        XCTAssertFalse(vm.canSubmit)
    }

    func testOptionWithNonZeroDeltaButNoNameBlocksSubmit() {
        // A priced-but-unnamed option is a real abandoned edit (not a fresh
        // "Add option" row), so it must NOT be silently pruned.
        let vm = ProductFormViewModel()
        vm.name = "Latte"
        var group = CappeProductOptionGroupInput(name: "Size")
        group.options = [CappeProductOptionInput(name: "", price_delta_cents: 100)]
        vm.optionGroups = [group]
        XCTAssertFalse(vm.optionsValid)
    }

    func testFullyNamedGroupAndOptionIsValid() {
        let vm = ProductFormViewModel()
        vm.name = "Latte"
        var group = CappeProductOptionGroupInput(name: "Size")
        group.options = [CappeProductOptionInput(name: "Large", price_delta_cents: 100)]
        vm.optionGroups = [group]
        XCTAssertTrue(vm.optionsValid)
        XCTAssertTrue(vm.canSubmit)
    }
}
