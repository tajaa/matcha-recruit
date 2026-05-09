import SwiftUI
import AVKit

struct MarkdownPreviewView: View {
    let sections: [MWProjectSection]
    let title: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(title)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.bottom, 4)

                ForEach(sections) { section in
                    SectionPreviewView(
                        section: section,
                        isLast: section.id == sections.last?.id
                    )
                }
            }
            .padding(24)
            .frame(maxWidth: 680, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(white: 0.08))
    }
}

// MARK: - Per-section view with cached block parse

/// Each section parses its markdown content once per content change and caches
/// the resulting blocks in @State, so unrelated state changes (selection,
/// tab toggle) don't re-run the regex parser.
private struct SectionPreviewView: View {
    let section: MWProjectSection
    let isLast: Bool
    @State private var blocks: [RenderedBlock] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !section.title.isEmpty {
                Text(section.title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
            }
            if let content = section.content, !content.isEmpty {
                ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                    renderBlock(block)
                }
            } else {
                Text("No content yet")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
        // .task(id:) fires reliably on first appear AND when content changes,
        // unlike .onAppear on a ForEach with an initially-empty @State (which
        // can no-op and leave the section body blank).
        .task(id: section.content ?? "") {
            blocks = renderBlocks(for: section.content ?? "")
        }
        if !isLast {
            Divider().opacity(0.2)
        }
    }

    // MARK: - Block parsing

    fileprivate enum RenderedBlock {
        case text(String, lineHeight: CGFloat)
        case image(alt: String, url: URL)
        case video(url: URL)
    }

    private func renderBlocks(for content: String) -> [RenderedBlock] {
        var blocks: [RenderedBlock] = []
        var textBuffer: [String] = []
        var lineHeightStack: [CGFloat] = [1.0]
        let flushText = {
            let joined = textBuffer.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !joined.isEmpty {
                blocks.append(.text(joined, lineHeight: lineHeightStack.last ?? 1.0))
            }
            textBuffer.removeAll()
        }
        for line in content.components(separatedBy: "\n") {
            if let lh = parseLineHeightOpen(line: line) {
                flushText()
                lineHeightStack.append(lh)
                continue
            }
            if parseLineHeightClose(line: line) {
                flushText()
                if lineHeightStack.count > 1 { lineHeightStack.removeLast() }
                continue
            }
            if let img = parseImage(line: line) {
                flushText()
                blocks.append(img)
                continue
            }
            if let vid = parseVideo(line: line) {
                flushText()
                blocks.append(vid)
                continue
            }
            textBuffer.append(line)
        }
        flushText()
        return blocks
    }

    /// Matches `<div style="line-height:N">` (also allows `line-height: N;` etc).
    private func parseLineHeightOpen(line: String) -> CGFloat? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        let lower = trimmed.lowercased()
        guard lower.hasPrefix("<div"), lower.contains("line-height") else { return nil }
        guard let range = lower.range(of: #"line-height\s*:\s*([0-9]*\.?[0-9]+)"#, options: .regularExpression) else {
            return nil
        }
        let match = String(lower[range])
        let numberString = match
            .replacingOccurrences(of: "line-height", with: "")
            .replacingOccurrences(of: ":", with: "")
            .trimmingCharacters(in: .whitespaces)
        return Double(numberString).map { CGFloat($0) }
    }

    private func parseLineHeightClose(line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces).lowercased()
        return trimmed == "</div>"
    }

    /// Matches standalone image line: ![alt](url)
    private func parseImage(line: String) -> RenderedBlock? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("!["), let endBracket = trimmed.firstIndex(of: "]"),
              trimmed.distance(from: trimmed.index(trimmed.startIndex, offsetBy: 2), to: endBracket) >= 0 else {
            return nil
        }
        let afterBracket = trimmed.index(after: endBracket)
        guard afterBracket < trimmed.endIndex, trimmed[afterBracket] == "(",
              let endParen = trimmed[afterBracket...].firstIndex(of: ")") else {
            return nil
        }
        let altStart = trimmed.index(trimmed.startIndex, offsetBy: 2)
        let alt = String(trimmed[altStart..<endBracket])
        let urlStart = trimmed.index(after: afterBracket)
        let urlString = String(trimmed[urlStart..<endParen])
        guard let url = URL(string: urlString) else { return nil }
        return .image(alt: alt, url: url)
    }

    /// Matches standalone video line: <video src="url" ...>
    private func parseVideo(line: String) -> RenderedBlock? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.lowercased().hasPrefix("<video"),
              let srcRange = trimmed.range(of: #"src=""#) else {
            return nil
        }
        let urlStart = srcRange.upperBound
        guard let urlEnd = trimmed.range(of: "\"", range: urlStart..<trimmed.endIndex)?.lowerBound else {
            return nil
        }
        let urlString = String(trimmed[urlStart..<urlEnd])
        guard let url = URL(string: urlString) else { return nil }
        return .video(url: url)
    }

    // MARK: - Block rendering

    @ViewBuilder
    private func renderBlock(_ block: RenderedBlock) -> some View {
        switch block {
        case .text(let raw, let lineHeight):
            // Convert line-height multiplier to SwiftUI `lineSpacing` (extra
            // space between lines, in points). 1.0 multiplier = 0 extra.
            let fontSize: CGFloat = 13
            let extra = max(0, (lineHeight - 1.0) * fontSize)
            if let attributed = try? AttributedString(
                markdown: raw,
                options: AttributedString.MarkdownParsingOptions(
                    interpretedSyntax: .inlineOnlyPreservingWhitespace
                )
            ) {
                Text(attributed)
                    .font(.system(size: fontSize))
                    .foregroundColor(Color(white: 0.85))
                    .lineSpacing(extra)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text(raw)
                    .font(.system(size: fontSize))
                    .foregroundColor(Color(white: 0.85))
                    .lineSpacing(extra)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        case .image(let alt, let url):
            VStack(alignment: .leading, spacing: 4) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFit()
                    case .failure:
                        HStack(spacing: 6) {
                            Image(systemName: "exclamationmark.triangle")
                            Text("Image failed to load")
                        }
                        .foregroundColor(.secondary)
                        .font(.system(size: 11))
                    default:
                        ProgressView().controlSize(.small)
                    }
                }
                .frame(maxWidth: .infinity)
                .cornerRadius(6)
                if !alt.isEmpty {
                    Text(alt)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .italic()
                }
            }
        case .video(let url):
            VideoPlayer(player: AVPlayer(url: url))
                .aspectRatio(16/9, contentMode: .fit)
                .frame(maxWidth: .infinity)
                .cornerRadius(6)
        }
    }
}
