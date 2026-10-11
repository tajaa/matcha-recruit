import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// The ways a thread document leaves the canvas: as text on the clipboard, or
/// as a file the person saves or opens in another app.
enum AssetExport {
    /// Plain text (markdown where the document is markdown) for Copy, or nil
    /// when the document has nothing worth copying yet.
    static func copyText(_ type: MWTaskType, state: [String: AnyCodable]) -> String? {
        let text: String?
        switch type {
        case .policy:
            text = string(state["policy_content"])
        case .review:
            text = reviewText(state)
        case .workbook:
            text = workbookText(state)
        case .presentation:
            text = presentationText(state)
        default:
            text = nil
        }
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }

    /// The header's Download for this document, if it has a file form.
    static func download(_ type: MWTaskType, state: [String: AnyCodable], title: String,
                         threadId: String?, pdfData: Data?) -> AssetAction? {
        switch type {
        case .offerLetter:
            guard let pdfData else { return nil }
            return AssetAction(label: "Save PDF", icon: "arrow.down.to.line") {
                try save(pdfData, name: "\(title).pdf", type: .pdf)
            }
        case .presentation, .workbook:
            guard let threadId, hasPresentationContent(type, state: state) else { return nil }
            return AssetAction(label: "Save PDF", icon: "arrow.down.to.line") {
                let data = try await MatchaWorkService.shared.getPresentationPdfData(threadId: threadId)
                try save(data, name: "\(title).pdf", type: .pdf)
            }
        case .policy:
            guard let markdown = string(state["policy_content"]) else { return nil }
            return AssetAction(label: "Save as Markdown", icon: "arrow.down.to.line") {
                try save(Data(markdown.utf8), name: "\(title).md",
                         type: UTType(filenameExtension: "md") ?? .plainText)
            }
        default:
            return nil
        }
    }

    /// "Open in Preview" for a document that is already a PDF in hand.
    static func openExternally(_ type: MWTaskType, title: String, pdfData: Data?) -> AssetAction? {
        guard type == .offerLetter, let pdfData else { return nil }
        return AssetAction(label: "Open in Preview", icon: "arrow.up.forward.app") {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(fileSafe(title)).pdf")
            try pdfData.write(to: url, options: .atomic)
            if let preview = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Preview") {
                _ = try await NSWorkspace.shared.open([url], withApplicationAt: preview,
                                                     configuration: NSWorkspace.OpenConfiguration())
            } else {
                NSWorkspace.shared.open(url)
            }
        }
    }

    // MARK: Helpers

    @MainActor
    private static func save(_ data: Data, name: String, type: UTType) throws {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [type]
        panel.nameFieldStringValue = fileSafe(name)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try data.write(to: url, options: .atomic)
    }

    /// A save-panel name: no path separators or colons, at most 80 characters.
    static func fileSafe(_ name: String) -> String {
        let cleaned = name
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Document" : String(cleaned.prefix(80))
    }

    private static func hasPresentationContent(_ type: MWTaskType, state: [String: AnyCodable]) -> Bool {
        let key = type == .presentation ? "slides" : "sections"
        return (state[key]?.value as? [AnyCodable])?.isEmpty == false
    }

    private static func string(_ value: AnyCodable?) -> String? {
        guard let raw = value?.value as? String else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : raw
    }

    private static func strings(_ value: AnyCodable?) -> [String] {
        (value?.value as? [AnyCodable])?.compactMap { $0.value as? String } ?? []
    }

    private static func reviewText(_ state: [String: AnyCodable]) -> String? {
        var lines: [String] = []
        if let title = string(state["review_title"]) { lines += ["# \(title)", ""] }
        if let rating = state["overall_rating"]?.value as? Int ?? (state["overall_rating"]?.value as? Double).map(Int.init),
           rating > 0 {
            lines += ["Overall rating: \(rating)/5", ""]
        }
        if let summary = string(state["summary"]) { lines += [summary, ""] }
        for (heading, key) in [("Strengths", "strengths"), ("Growth areas", "growth_areas"), ("Next steps", "next_steps")] {
            let items = strings(state[key])
            guard !items.isEmpty else { continue }
            lines.append("## \(heading)")
            lines += items.map { "- \($0)" }
            lines.append("")
        }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    private static func workbookText(_ state: [String: AnyCodable]) -> String? {
        var lines: [String] = []
        if let title = string(state["workbook_title"]) { lines += ["# \(title)", ""] }
        for item in (state["sections"]?.value as? [AnyCodable]) ?? [] {
            guard let dict = item.value as? [String: AnyCodable] else { continue }
            if let title = string(dict["title"]) { lines.append("## \(title)") }
            if let body = string(dict["body"]) ?? string(dict["content"]) { lines.append(body) }
            lines.append("")
        }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    private static func presentationText(_ state: [String: AnyCodable]) -> String? {
        var lines: [String] = []
        if let title = string(state["presentation_title"]) { lines += ["# \(title)", ""] }
        for (index, item) in ((state["slides"]?.value as? [AnyCodable]) ?? []).enumerated() {
            guard let dict = item.value as? [String: AnyCodable] else { continue }
            lines.append("## \(index + 1). \(string(dict["title"]) ?? "Slide")")
            lines += strings(dict["bullets"]).map { "- \($0)" }
            if let notes = string(dict["speaker_notes"]) { lines.append("> \(notes)") }
            lines.append("")
        }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }
}
