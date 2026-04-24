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
                    VStack(alignment: .leading, spacing: 10) {
                        if !section.title.isEmpty {
                            Text(section.title)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.white)
                        }
                        if let content = section.content, !content.isEmpty {
                            ForEach(Array(renderBlocks(for: content).enumerated()), id: \.offset) { _, block in
                                renderBlock(block)
                            }
                        } else {
                            Text("No content yet")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .italic()
                        }
                    }
                    if section.id != sections.last?.id {
                        Divider().opacity(0.2)
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: 680, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(white: 0.08))
    }

    // MARK: - Block parsing

    private enum RenderedBlock {
        case text(String)
        case image(alt: String, url: URL)
        case video(url: URL)
    }

    private func renderBlocks(for content: String) -> [RenderedBlock] {
        var blocks: [RenderedBlock] = []
        var textBuffer: [String] = []
        let flushText = {
            let joined = textBuffer.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !joined.isEmpty {
                blocks.append(.text(joined))
            }
            textBuffer.removeAll()
        }
        for line in content.components(separatedBy: "\n") {
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
        case .text(let raw):
            if let attributed = try? AttributedString(
                markdown: raw,
                options: AttributedString.MarkdownParsingOptions(
                    interpretedSyntax: .inlineOnlyPreservingWhitespace
                )
            ) {
                Text(attributed)
                    .font(.system(size: 13))
                    .foregroundColor(Color(white: 0.85))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                Text(raw)
                    .font(.system(size: 13))
                    .foregroundColor(Color(white: 0.85))
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
