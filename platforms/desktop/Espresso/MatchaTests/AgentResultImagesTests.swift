import XCTest
@testable import Matcha

/// Photos and page screenshots in an assistant answer decode, survive the
/// metadata round trip, and an unknown block still decodes to `.unknown`.
final class AgentResultImagesTests: XCTestCase {

    private let json = """
    {"headline": "Tower 737", "summary": "Here it is.", "caveats": [], "confidence": "medium",
     "blocks": [
        {"type": "photos", "photos": [{"url": "https://cdn.example/1.webp", "page_url": "https://www.zillow.com/a/", "alt": "Lobby"}]},
        {"type": "screenshots", "screenshots": [{"url": "https://cdn.example/s1.webp", "page_url": "https://tower737.example/units", "caption": "The unit list"}]},
        {"type": "holograms", "items": []}
     ]}
    """

    func testPhotosAndScreenshotsDecodeAndRoundTrip() throws {
        let result = try JSONDecoder().decode(AgentChatResultV2.self, from: Data(json.utf8))
        XCTAssertEqual(result.blocks.count, 3)
        guard case .photos(let photos) = result.blocks[0], case .screenshots(let shots) = result.blocks[1] else {
            return XCTFail("expected photos then screenshots, got \(result.blocks)")
        }
        XCTAssertEqual(photos.first?.label, "Lobby")
        XCTAssertEqual(photos.first?.pageUrl, "https://www.zillow.com/a/")
        XCTAssertEqual(shots.first?.label, "The unit list")
        XCTAssertEqual(result.blocks[2], .unknown("holograms"))

        let again = try JSONDecoder().decode(AgentChatResultV2.self, from: JSONEncoder().encode(result))
        XCTAssertEqual(again.blocks, result.blocks)
    }

    func testABlankLabelFallsBackOrIsNil() {
        XCTAssertEqual(AgentImage(url: "https://cdn.example/x.webp", pageUrl: nil, alt: "Front", caption: "").label, "Front")
        XCTAssertNil(AgentImage(url: "https://cdn.example/x.webp", pageUrl: nil, alt: nil, caption: nil).label)
    }
}
