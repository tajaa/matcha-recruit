import SwiftUI

/// Read-mode renderer for journal entry content. Parses markdown blocks
/// line-by-line and renders each block as a distinct SwiftUI view so we
/// can mix interactive checkboxes, async images, and styled text without
/// fighting AttributedString.
///
/// Supports stock markdown (headers, bullets, numbered, blockquote,
/// fenced code, links, bold/italic/strike), plus three extensions:
///   - `==text==`        → background-highlighted run
///   - `- [ ]` / `- [x]` → interactive checkbox (`onToggleTodo(idx)`)
///   - `![alt](url)`     → AsyncImage block
struct JournalContentView: View {
    let content: String
    let fontFamily: String
    let fontSize: CGFloat
    let lineSpacing: CGFloat
    /// Called when a checkbox is tapped. `index` is the order of the todo
    /// across all lines of `content` (0-based).
    let onToggleTodo: (Int) -> Void

    @State private var blocks: [JournalBlock] = []

    init(
        content: String,
        fontFamily: String = "system",
        fontSize: CGFloat = 13,
        lineSpacing: CGFloat = 3,
        onToggleTodo: @escaping (Int) -> Void = { _ in },
    ) {
        self.content = content
        self.fontFamily = fontFamily
        self.fontSize = fontSize
        self.lineSpacing = lineSpacing
        self.onToggleTodo = onToggleTodo
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, b in
                render(b)
            }
        }
        .task(id: content) {
            blocks = JournalBlockParser.parse(content)
        }
    }

    // MARK: - Block rendering

    @ViewBuilder
    private func render(_ block: JournalBlock) -> some View {
        switch block {
        case .paragraph(let text):
            inlineText(text)
                .lineSpacing(lineSpacing)
        case .heading(let level, let text):
            inlineText(text, sizeOverride: headingSize(level), weight: .bold)
                .padding(.top, level == 1 ? 4 : 2)
        case .bullet(let text):
            HStack(alignment: .top, spacing: 6) {
                Text("•").font(.system(size: fontSize)).foregroundColor(.white.opacity(0.7))
                inlineText(text).lineSpacing(lineSpacing)
            }
        case .numbered(let n, let text):
            HStack(alignment: .top, spacing: 6) {
                Text("\(n).")
                    .font(.system(size: fontSize))
                    .foregroundColor(.white.opacity(0.55))
                    .frame(minWidth: 16, alignment: .trailing)
                inlineText(text).lineSpacing(lineSpacing)
            }
        case .todo(let checked, let text, let idx):
            HStack(alignment: .top, spacing: 6) {
                Button { onToggleTodo(idx) } label: {
                    Image(systemName: checked ? "checkmark.square.fill" : "square")
                        .font(.system(size: fontSize))
                        .foregroundColor(checked ? Color.matcha500 : .white.opacity(0.5))
                }
                .buttonStyle(.plain)
                inlineText(text)
                    .strikethrough(checked, color: .white.opacity(0.4))
                    .opacity(checked ? 0.55 : 1.0)
                    .lineSpacing(lineSpacing)
            }
        case .quote(let text):
            HStack(alignment: .top, spacing: 6) {
                Rectangle().fill(Color.matcha500.opacity(0.6)).frame(width: 2)
                inlineText(text)
                    .italic()
                    .foregroundColor(.white.opacity(0.7))
                    .lineSpacing(lineSpacing)
            }
            .padding(.leading, 2)
        case .codeBlock(let code):
            Text(code)
                .font(.system(size: fontSize - 1, design: .monospaced))
                .foregroundColor(.white.opacity(0.85))
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.black.opacity(0.35))
                .cornerRadius(4)
        case .image(let alt, let url):
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    Rectangle().fill(Color.white.opacity(0.05))
                        .frame(height: 120)
                        .overlay(ProgressView().tint(.secondary))
                        .cornerRadius(6)
                case .success(let img):
                    img.resizable()
                        .scaledToFit()
                        .frame(maxHeight: 320)
                        .cornerRadius(6)
                case .failure:
                    HStack {
                        Image(systemName: "photo.badge.exclamationmark")
                        Text(alt.isEmpty ? "Image failed to load" : alt)
                            .font(.system(size: 11))
                    }
                    .foregroundColor(.red.opacity(0.7))
                    .padding(8)
                    .background(Color.red.opacity(0.05))
                    .cornerRadius(4)
                @unknown default:
                    EmptyView()
                }
            }
        case .divider:
            Divider().opacity(0.25).padding(.vertical, 4)
        }
    }

    // MARK: - Inline run rendering

    /// Render an inline run with markdown-supported bold/italic/strike +
    /// our `==highlight==` extension. AttributedString does the heavy
    /// lifting; we post-process to apply background color on highlight
    /// matches, scanning right-to-left so character indices stay valid as
    /// markers are stripped.
    private func inlineText(
        _ source: String,
        sizeOverride: CGFloat? = nil,
        weight: Font.Weight = .regular,
    ) -> Text {
        var attr: AttributedString
        if let parsed = try? AttributedString(
            markdown: source,
            options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace,
            ),
        ) {
            attr = parsed
        } else {
            attr = AttributedString(source)
        }
        applyHighlight(&attr)
        let size = sizeOverride ?? fontSize
        let font: Font
        switch fontFamily {
        case "serif":      font = .custom("Georgia", size: size).weight(weight)
        case "monospaced": font = .system(size: size, weight: weight, design: .monospaced)
        default:           font = .system(size: size, weight: weight)
        }
        return Text(attr).font(font).foregroundColor(.white.opacity(0.92))
    }

    /// Walk the attributed string right-to-left for `==…==`, applying
    /// `backgroundColor` to the inner range *in place* (preserving any
    /// nested bold/italic/strike runs) and then deleting the surrounding
    /// `==` markers. Right-to-left keeps earlier ranges valid as we mutate.
    private func applyHighlight(_ attr: inout AttributedString) {
        let raw = String(attr.characters)
        // Capture group: lazy match between markers, no embedded `==`.
        guard let regex = try? NSRegularExpression(pattern: "==(.+?)==") else { return }
        let nsRaw = raw as NSString
        let matches = regex.matches(in: raw, range: NSRange(location: 0, length: nsRaw.length))
        for m in matches.reversed() {
            guard let outerStr = Range(m.range, in: raw),
                  let innerStr = Range(m.range(at: 1), in: raw),
                  let outerAttr = Range<AttributedString.Index>(outerStr, in: attr),
                  let innerAttr = Range<AttributedString.Index>(innerStr, in: attr) else { continue }
            // Apply highlight to inner content (keeps nested attributes).
            attr[innerAttr].backgroundColor = Color.yellow.opacity(0.35)
            // Strip the trailing `==`, then the leading one. Right-side
            // delete first so the leading bound stays valid.
            let trailStart = attr.index(outerAttr.upperBound, offsetByCharacters: -2)
            attr.removeSubrange(trailStart..<outerAttr.upperBound)
            let leadEnd = attr.index(outerAttr.lowerBound, offsetByCharacters: 2)
            attr.removeSubrange(outerAttr.lowerBound..<leadEnd)
        }
    }

    private func headingSize(_ level: Int) -> CGFloat {
        switch level {
        case 1: return fontSize + 6
        case 2: return fontSize + 3
        default: return fontSize + 1
        }
    }
}

// MARK: - Block model + parser

enum JournalBlock {
    case paragraph(String)
    case heading(level: Int, text: String)
    case bullet(String)
    case numbered(Int, String)
    case todo(checked: Bool, text: String, index: Int)
    case quote(String)
    case codeBlock(String)
    case image(alt: String, url: URL)
    case divider
}

enum JournalBlockParser {
    /// Line-by-line block parser. Walks the source once, collecting
    /// paragraph runs and emitting structured blocks for headings, lists,
    /// todos, blockquote, fenced code, images, and dividers.
    static func parse(_ content: String) -> [JournalBlock] {
        let lines = content.components(separatedBy: "\n")
        var out: [JournalBlock] = []
        var paragraphBuffer: [String] = []
        var inFence = false
        var fenceBuffer: [String] = []
        var todoCounter = 0
        var numberedRun = 0

        func flushParagraph() {
            if !paragraphBuffer.isEmpty {
                let joined = paragraphBuffer.joined(separator: "\n").trimmingCharacters(in: .whitespaces)
                if !joined.isEmpty { out.append(.paragraph(joined)) }
                paragraphBuffer.removeAll()
            }
        }

        for rawLine in lines {
            let line = rawLine
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            // Fenced code block (``` start/end).
            if trimmed.hasPrefix("```") {
                if inFence {
                    out.append(.codeBlock(fenceBuffer.joined(separator: "\n")))
                    fenceBuffer.removeAll()
                    inFence = false
                } else {
                    flushParagraph()
                    numberedRun = 0
                    inFence = true
                }
                continue
            }
            if inFence {
                fenceBuffer.append(line)
                continue
            }

            // Divider.
            if trimmed == "---" || trimmed == "***" {
                flushParagraph()
                numberedRun = 0
                out.append(.divider)
                continue
            }

            // Standalone image: a line whose only content is `![alt](url)`.
            if let img = parseImageLine(trimmed) {
                flushParagraph()
                numberedRun = 0
                out.append(img)
                continue
            }

            // Headings.
            if let (level, text) = parseHeading(trimmed) {
                flushParagraph()
                numberedRun = 0
                out.append(.heading(level: level, text: text))
                continue
            }

            // Todos — must check before generic bullet.
            if let (checked, text) = parseTodo(trimmed) {
                flushParagraph()
                numberedRun = 0
                out.append(.todo(checked: checked, text: text, index: todoCounter))
                todoCounter += 1
                continue
            }

            // Bullets.
            if let text = parseBullet(trimmed) {
                flushParagraph()
                numberedRun = 0
                out.append(.bullet(text))
                continue
            }

            // Numbered.
            if let text = parseNumbered(trimmed) {
                flushParagraph()
                numberedRun += 1
                out.append(.numbered(numberedRun, text))
                continue
            }

            // Blockquote.
            if trimmed.hasPrefix("> ") {
                flushParagraph()
                numberedRun = 0
                out.append(.quote(String(trimmed.dropFirst(2))))
                continue
            }

            // Blank line — paragraph break.
            if trimmed.isEmpty {
                flushParagraph()
                numberedRun = 0
                continue
            }

            // Default: paragraph line.
            numberedRun = 0
            paragraphBuffer.append(line)
        }

        // Flush trailing buffers.
        flushParagraph()
        if inFence, !fenceBuffer.isEmpty {
            out.append(.codeBlock(fenceBuffer.joined(separator: "\n")))
        }
        return out
    }

    private static func parseHeading(_ trimmed: String) -> (Int, String)? {
        if trimmed.hasPrefix("### ") { return (3, String(trimmed.dropFirst(4))) }
        if trimmed.hasPrefix("## ")  { return (2, String(trimmed.dropFirst(3))) }
        if trimmed.hasPrefix("# ")   { return (1, String(trimmed.dropFirst(2))) }
        return nil
    }

    private static func parseTodo(_ trimmed: String) -> (Bool, String)? {
        if trimmed.hasPrefix("- [ ] ") || trimmed.hasPrefix("* [ ] ") {
            return (false, String(trimmed.dropFirst(6)))
        }
        if trimmed.hasPrefix("- [x] ") || trimmed.hasPrefix("- [X] ")
            || trimmed.hasPrefix("* [x] ") || trimmed.hasPrefix("* [X] ") {
            return (true, String(trimmed.dropFirst(6)))
        }
        // Tolerate missing trailing space, e.g. `- [ ]` alone.
        if trimmed == "- [ ]" || trimmed == "* [ ]" { return (false, "") }
        if trimmed == "- [x]" || trimmed == "- [X]" || trimmed == "* [x]" || trimmed == "* [X]" {
            return (true, "")
        }
        return nil
    }

    private static func parseBullet(_ trimmed: String) -> String? {
        if trimmed.hasPrefix("- ") { return String(trimmed.dropFirst(2)) }
        if trimmed.hasPrefix("* ") && !trimmed.hasPrefix("**") {
            return String(trimmed.dropFirst(2))
        }
        return nil
    }

    private static func parseNumbered(_ trimmed: String) -> String? {
        // Match `<digits>. <rest>`.
        guard let dotIdx = trimmed.firstIndex(of: ".") else { return nil }
        let head = trimmed[..<dotIdx]
        guard !head.isEmpty, head.allSatisfy({ $0.isNumber }) else { return nil }
        let rest = trimmed.index(after: dotIdx)
        guard rest < trimmed.endIndex, trimmed[rest] == " " else { return nil }
        return String(trimmed[trimmed.index(after: rest)...])
    }

    /// Recognize an image-only line `![alt](url)`. Anything before/after
    /// kicks it back to paragraph rendering (which will still embed an
    /// inline image via the AttributedString markdown pass, though without
    /// our nicer block layout).
    private static func parseImageLine(_ trimmed: String) -> JournalBlock? {
        guard trimmed.hasPrefix("!["), trimmed.hasSuffix(")") else { return nil }
        // Greedy parse: find `](` separator.
        guard let altClose = trimmed.range(of: "](") else { return nil }
        let alt = String(trimmed[trimmed.index(trimmed.startIndex, offsetBy: 2)..<altClose.lowerBound])
        let urlStr = String(trimmed[altClose.upperBound..<trimmed.index(before: trimmed.endIndex)])
        guard let url = URL(string: urlStr), url.scheme?.hasPrefix("http") == true else { return nil }
        return .image(alt: alt, url: url)
    }
}
