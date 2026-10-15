import XCTest
import AppKit
import ImageIO
import UniformTypeIdentifiers
@testable import Matcha

/// Files given to Espresso: what the composer takes, how a private file is
/// named, and the short links that show it. No network.
@MainActor
final class EspressoFilesTests: XCTestCase {

    private func pending(_ name: String, bytes: Int) -> PendingChannelAttachment {
        PendingChannelAttachment(data: Data(count: bytes), filename: name, mimeType: "application/octet-stream")
    }

    func testAPrivateFileIsNamedNotLinked() {
        let file = ChannelAttachment(url: "espresso-input:3f2a", filename: "cv.pdf", contentType: "application/pdf", size: 9)
        XCTAssertEqual(file.privateInputId, "3f2a")
        let ordinary = ChannelAttachment(url: "https://cdn.test/a.png", filename: "a.png", contentType: "image/png", size: 9)
        XCTAssertNil(ordinary.privateInputId)
        let empty = ChannelAttachment(url: "espresso-input:", filename: "x", contentType: "text/plain", size: 0)
        XCTAssertNil(empty.privateInputId)
    }

    func testEspressoTakesWhatItCanRead() {
        let rules = AttachmentRules.espresso
        XCTAssertNil(rules.refusal(filename: "cv.PDF", size: 1_000, pending: []))
        XCTAssertNil(rules.refusal(filename: "IMG_1.heic", size: 1_000, pending: []))
        XCTAssertEqual(rules.refusal(filename: "old.doc", size: 10, pending: []),
                       "Save older Word files as .docx or PDF first")
        XCTAssertEqual(rules.refusal(filename: "setup.zip", size: 10, pending: []),
                       "Espresso reads PDF, Word, text, Markdown, CSV and JSON files, and images")
        let five = (0..<5).map { pending("f\($0).txt", bytes: 10) }
        XCTAssertEqual(rules.refusal(filename: "six.txt", size: 10, pending: five), "Espresso takes up to 5 files at a time")
        XCTAssertEqual(rules.refusal(filename: "big.pdf", size: 11 * 1024 * 1024, pending: []),
                       "big.pdf is too large (max 10 MB)")
        let heavy = [pending("a.pdf", bytes: 9 * 1024 * 1024), pending("b.pdf", bytes: 9 * 1024 * 1024)]
        XCTAssertEqual(rules.refusal(filename: "c.pdf", size: 9 * 1024 * 1024, pending: heavy),
                       "Those files are over 25 MB together")
    }

    func testChannelsStillTakeNearlyAnything() {
        let rules = AttachmentRules.channel
        XCTAssertNil(rules.refusal(filename: "archive.zip", size: 40 * 1024 * 1024, pending: []))
        XCTAssertEqual(rules.refusal(filename: "tool.exe", size: 1, pending: []), "File type .exe isn't allowed")
        let ten = (0..<10).map { pending("f\($0).txt", bytes: 1) }
        XCTAssertEqual(rules.refusal(filename: "x.txt", size: 1, pending: ten), "Max 10 attachments per message")
        XCTAssertEqual(rules.refusal(filename: "movie.mov", size: 51 * 1024 * 1024, pending: []),
                       "movie.mov is too large (max 50 MB)")
    }

    func testHEICPhotosBecomeJPEG() throws {
        let plain = pending("notes.txt", bytes: 3)
        XCTAssertEqual(ChannelDetailView.convertingHEIC(plain), plain)
        XCTAssertNil(ChannelDetailView.convertingHEIC(pending("broken.heic", bytes: 12)))

        // A real HEIC, written with ImageIO.
        let image = NSImage(size: NSSize(width: 20, height: 10))
        image.lockFocus(); NSColor.red.setFill(); NSRect(x: 0, y: 0, width: 20, height: 10).fill(); image.unlockFocus()
        let cg = try XCTUnwrap(image.cgImage(forProposedRect: nil, context: nil, hints: nil))
        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(data, UTType.heic.identifier as CFString, 1, nil) else {
            throw XCTSkip("This Mac can't write HEIC")
        }
        CGImageDestinationAddImage(dest, cg, nil)
        guard CGImageDestinationFinalize(dest) else { throw XCTSkip("This Mac can't write HEIC") }
        let photo = PendingChannelAttachment(data: data as Data, filename: "IMG_2.HEIC", mimeType: "image/heic")
        let converted = try XCTUnwrap(ChannelDetailView.convertingHEIC(photo))
        XCTAssertEqual(converted.filename, "IMG_2.jpg")
        XCTAssertEqual(converted.mimeType, "image/jpeg")
        XCTAssertEqual(Array(converted.data.prefix(2)), [0xFF, 0xD8])
    }

    func testAnUploadRefusalReadsAsTheServersSentence() {
        XCTAssertEqual(ChannelDetailView.uploadFailure(APIError.httpError(400, "Espresso takes up to 5 files at a time.")),
                       "Espresso takes up to 5 files at a time.")
        XCTAssertTrue(ChannelDetailView.uploadFailure(APIError.httpError(500, "{\"detail\": []}")).hasPrefix("Upload failed"))
        XCTAssertTrue(ChannelDetailView.uploadFailure(URLError(.timedOut)).hasPrefix("Upload failed"))
    }

    func testFileLinksAreReusedUntilAMinuteBeforeTheyExpire() throws {
        let links = PrivateInputLinks()
        let url = try XCTUnwrap(URL(string: "https://signed.test/cv.pdf"))
        let now = Date(timeIntervalSince1970: 1_000)
        links.store(url, for: "a", lifetime: 300, now: now)
        XCTAssertEqual(links.url(for: "a", now: now.addingTimeInterval(200)), url)
        XCTAssertNil(links.url(for: "a", now: now.addingTimeInterval(241)))
        XCTAssertNil(links.url(for: "b", now: now))
        links.store(url, for: "c", lifetime: 300, now: now)
        links.clear()
        XCTAssertNil(links.url(for: "c", now: now))
    }
}
