import XCTest
@testable import TellUs

final class AvatarTests: XCTestCase {
    func testInitialsHandleEmptyAndEmojiNames() {
        XCTAssertEqual(Avatar.initials(from: nil), "?")
        XCTAssertEqual(Avatar.initials(from: "..."), "?")
        XCTAssertEqual(Avatar.initials(from: "Jane Doe"), "JD")
        XCTAssertEqual(Avatar.initials(from: "🦊 Finch"), "🦊F")
    }

    func testPaletteIndexIsDeterministicAndDistributed() {
        let ids = (0..<200).map { "00000000-0000-0000-0000-\(String(format: "%012d", $0))" }
        let indexes = ids.map(Avatar.paletteIndex(for:))
        XCTAssertTrue(indexes.allSatisfy { (0..<6).contains($0) })
        XCTAssertGreaterThanOrEqual(Set(indexes).count, 4)
        XCTAssertEqual(Avatar.paletteIndex(for: ids[42]), Avatar.paletteIndex(for: ids[42]))
    }
}
