import CoreGraphics
import Foundation

// MARK: - Page geometry (US Letter, 12pt Courier)

/// Standard US screenplay metrics in points. 1" = 72pt; 12pt Courier advances
/// 7.2pt/char (10 chars/inch). These drive both the on-screen page view and the
/// exported PDF so the two match.
enum ScreenplayPageMetrics {
    static let pageWidth: CGFloat = 612      // 8.5"
    static let pageHeight: CGFloat = 792     // 11"
    static let marginTop: CGFloat = 72       // 1"
    static let marginBottom: CGFloat = 72    // 1"
    static let marginLeft: CGFloat = 108     // 1.5"
    static let marginRight: CGFloat = 72     // 1"
    static let lineHeight: CGFloat = 12
    static let charWidth: CGFloat = 7.2
    static var maxRows: Int { Int((pageHeight - marginTop - marginBottom) / lineHeight) }  // ~54

    /// Left edge (from the page's left side) where an element's text starts.
    static func leftInset(_ e: ScreenplayElement) -> CGFloat {
        switch e {
        case .character:     return 266   // ~3.7"
        case .parenthetical: return 223   // ~3.1"
        case .dialogue:      return 180   // ~2.5"
        default:             return marginLeft
        }
    }

    /// Text column width for an element.
    static func width(_ e: ScreenplayElement) -> CGFloat {
        switch e {
        case .character:     return pageWidth - 266 - marginRight
        case .parenthetical: return 200   // ~2.8"
        case .dialogue:      return 252   // ~3.5"
        default:             return pageWidth - marginLeft - marginRight  // 6"
        }
    }

    static func charsPerRow(_ e: ScreenplayElement) -> Int {
        max(1, Int(width(e) / charWidth))
    }
}

// MARK: - Paginated model

/// One visual row on a page (already wrapped to its element's column width).
struct ScreenplayPageLine: Hashable {
    var element: ScreenplayElement
    var text: String
    var dual: Bool = false
    var isBlank: Bool = false
    var sceneNumber: String? = nil   // set on the first row of a scene heading
}

struct ScreenplayPage: Identifiable, Hashable {
    let id = UUID()
    var number: Int
    var lines: [ScreenplayPageLine]
}

// MARK: - Paginator

/// Lays a screenplay's body out into US-Letter pages: wraps each element to its
/// column, inserts a blank row between blocks, numbers scenes, and breaks pages
/// at ~54 rows — keeping a character cue with its first line of dialogue and
/// splitting long dialogue with (MORE) / CHARACTER (CONT'D).
///
/// v1 renders dual dialogue sequentially (stacked), not side-by-side.
enum ScreenplayPaginator {

    static func paginate(_ doc: ScreenplayDocument) -> [ScreenplayPage] {
        let rows = expand(doc)
        return breakIntoPages(rows)
    }

    // Expand lines → wrapped visual rows with separators + scene numbers.
    private static func expand(_ doc: ScreenplayDocument) -> [ScreenplayPageLine] {
        var rows: [ScreenplayPageLine] = []
        var sceneNum = 0
        for line in doc.lines {
            switch line.element {
            case .section, .synopsis:
                continue   // organizational only — not printed
            case .pageBreak:
                rows.append(ScreenplayPageLine(element: .pageBreak, text: ""))
                continue
            default:
                break
            }
            // Blank separator before a block-level element (not dialogue/parenthetical).
            let blockLevel = !(line.element == .dialogue || line.element == .parenthetical)
            if blockLevel, !rows.isEmpty {
                rows.append(ScreenplayPageLine(element: .action, text: "", isBlank: true))
            }
            var sceneLabel: String? = nil
            if line.element == .sceneHeading {
                sceneNum += 1
                sceneLabel = "\(sceneNum)"
            }
            let shown = line.element.isUppercased ? line.text.uppercased() : line.text
            let wrapped = wrap(shown, ScreenplayPageMetrics.charsPerRow(line.element))
            for (i, w) in wrapped.enumerated() {
                rows.append(ScreenplayPageLine(
                    element: line.element, text: w, dual: line.dual,
                    sceneNumber: i == 0 ? sceneLabel : nil,
                ))
            }
        }
        return rows
    }

    private static func breakIntoPages(_ rows: [ScreenplayPageLine]) -> [ScreenplayPage] {
        // Reserve one row so an appended "(MORE)" on a dialogue split can't push
        // a page past its physical row budget (which would clip the last line).
        let maxRows = ScreenplayPageMetrics.maxRows - 1
        var pages: [[ScreenplayPageLine]] = [[]]
        var count = 0
        var lastCharacter = ""

        func newPage() { pages.append([]); count = 0 }
        func place(_ line: ScreenplayPageLine) {
            pages[pages.count - 1].append(line)
            if !line.isBlank { count += 1 } else { count += 1 }
        }

        var i = 0
        while i < rows.count {
            let row = rows[i]

            if row.element == .pageBreak {
                if !pages[pages.count - 1].isEmpty { newPage() }
                i += 1
                continue
            }
            if row.element == .character { lastCharacter = row.text }

            // Keep a character cue with its first line: if a cue lands within 2
            // rows of the bottom, push the whole cue block to the next page.
            if row.element == .character, count >= maxRows - 2, !pages[pages.count - 1].isEmpty {
                newPage()
            }
            // Don't orphan a scene heading at the very bottom.
            if row.element == .sceneHeading, count >= maxRows - 1, !pages[pages.count - 1].isEmpty {
                newPage()
            }

            if count >= maxRows {
                // Page full. Split dialogue with (MORE)/(CONT'D); else just break.
                if row.element == .dialogue, !lastCharacter.isEmpty {
                    pages[pages.count - 1].append(ScreenplayPageLine(element: .parenthetical, text: "(MORE)"))
                    newPage()
                    pages[pages.count - 1].append(ScreenplayPageLine(element: .character, text: contd(lastCharacter)))
                    count = 1
                } else {
                    newPage()
                    // Drop a leading blank separator at the top of a fresh page.
                    if row.isBlank { i += 1; continue }
                }
            }
            place(row)
            i += 1
        }

        // Drop a trailing empty page.
        if pages.count > 1, pages.last?.isEmpty == true { pages.removeLast() }
        return pages.enumerated().map { ScreenplayPage(number: $0.offset + 1, lines: $0.element) }
    }

    private static func contd(_ name: String) -> String {
        name.uppercased().contains("(CONT'D)") ? name : "\(name) (CONT'D)"
    }

    /// Greedy word-wrap to a character budget; hard-breaks over-long words.
    static func wrap(_ text: String, _ cpr: Int) -> [String] {
        if text.isEmpty { return [""] }
        var rows: [String] = []
        var current = ""
        for word in text.split(separator: " ", omittingEmptySubsequences: false) {
            let w = String(word)
            if current.isEmpty {
                current = w
            } else if current.count + 1 + w.count <= cpr {
                current += " " + w
            } else {
                rows.append(current)
                current = w
            }
            while current.count > cpr {
                rows.append(String(current.prefix(cpr)))
                current = String(current.dropFirst(cpr))
            }
        }
        if !current.isEmpty || rows.isEmpty { rows.append(current) }
        return rows
    }
}
