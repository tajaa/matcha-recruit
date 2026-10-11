import SwiftUI

/// What a thread's document is, for the asset canvas and the chat's asset
/// cards: a name, a glyph, a tint, and the title the document gives itself.
struct AssetKind {
    let type: MWTaskType
    let name: String
    let icon: String
    let tint: Color

    init(_ type: MWTaskType) {
        self.type = type
        switch type {
        case .offerLetter:
            (name, icon, tint) = ("Offer letter", "signature", Color(red: 0.20, green: 0.66, blue: 0.47))
        case .review:
            (name, icon, tint) = ("Review", "star.bubble", Color(red: 0.93, green: 0.64, blue: 0.16))
        case .workbook:
            (name, icon, tint) = ("Workbook", "book.closed", Color(red: 0.43, green: 0.46, blue: 0.95))
        case .onboarding:
            (name, icon, tint) = ("Onboarding", "person.badge.plus", Color(red: 0.13, green: 0.64, blue: 0.70))
        case .presentation:
            (name, icon, tint) = ("Presentation", "play.rectangle", Color(red: 0.95, green: 0.44, blue: 0.27))
        case .handbook:
            (name, icon, tint) = ("Handbook", "books.vertical", Color(red: 0.29, green: 0.55, blue: 0.95))
        case .policy:
            (name, icon, tint) = ("Policy", "checkmark.shield", Color(red: 0.60, green: 0.42, blue: 0.95))
        case .resumeBatch:
            (name, icon, tint) = ("Resume batch", "person.2", Color(red: 0.90, green: 0.36, blue: 0.55))
        case .inventory:
            (name, icon, tint) = ("Inventory", "shippingbox", Color(red: 0.55, green: 0.62, blue: 0.30))
        case .project:
            (name, icon, tint) = ("Project", "folder", Color(red: 0.48, green: 0.52, blue: 0.60))
        case .blog:
            (name, icon, tint) = ("Blog post", "pencil.line", Color(red: 0.48, green: 0.52, blue: 0.60))
        case .languageTutor, .chat:
            (name, icon, tint) = ("Document", "doc.text", Color(red: 0.48, green: 0.52, blue: 0.60))
        }
    }

    /// The document's own name for itself, when it has one yet.
    func title(from state: [String: AnyCodable]) -> String? {
        func text(_ key: String) -> String? {
            guard let raw = state[key]?.value as? String else { return nil }
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        switch type {
        case .offerLetter:
            let parts = [text("candidate_name"), text("position_title")].compactMap { $0 }
            return parts.isEmpty ? nil : parts.joined(separator: " — ")
        case .review: return text("review_title")
        case .workbook: return text("workbook_title")
        case .presentation: return text("presentation_title")
        case .handbook: return text("handbook_title")
        case .policy: return text("policy_title")
        case .resumeBatch: return text("batch_title")
        case .inventory: return text("inventory_title")
        case .project: return text("project_title")
        case .onboarding, .blog, .languageTutor, .chat: return nil
        }
    }
}

/// One thing the header can do with the document. `run` may throw; the
/// canvas shows the error under the header instead of dropping it.
struct AssetAction {
    let label: String
    let icon: String
    let run: @MainActor () async throws -> Void
}

/// What the canvas around a preview needs to know about its thread. Every
/// field has a default so a call site that has none of it (a project's chat)
/// still gets the chrome, just without history or the live state.
struct AssetCanvasContext {
    var threadId: String?
    var threadTitle: String?
    var version: Int?
    var updatedAt: String?
    var status: String?
    var versions: [MWDocumentVersion] = []
    var isStreaming = false
    var isFocused = false
    var onToggleFocus: (() -> Void)?
    var onRevert: ((Int) -> Void)?
}

/// The thread's document as the chat sees it, for the asset card that marks
/// each reply that changed it. Set by `ThreadDetailView`; nil elsewhere, where
/// `MessageBubbleView` keeps its plain "Document updated" line.
struct ThreadAssetContext {
    let kind: AssetKind
    let title: String?
    let versions: [MWDocumentVersion]
    let currentVersion: Int
    let open: () -> Void
}

private struct ThreadAssetKey: EnvironmentKey {
    static let defaultValue: ThreadAssetContext? = nil
}

extension EnvironmentValues {
    var threadAsset: ThreadAssetContext? {
        get { self[ThreadAssetKey.self] }
        set { self[ThreadAssetKey.self] = newValue }
    }
}

extension AppState {
    /// A recessed well on a document surface (a list block, a stat tile),
    /// replacing the fixed zinc800 the previews used to paint in every theme.
    var assetWell: Color { themeText.opacity(isLightFamily ? 0.035 : 0.05) }
}

enum AssetTime {
    /// "edited 2m ago" from the thread's ISO `updated_at`; nil when unparsable.
    static func edited(_ iso: String?, now: Date = Date()) -> String? {
        guard let iso, let date = parse(iso) else { return nil }
        let seconds = max(0, now.timeIntervalSince(date))
        if seconds < 45 { return "edited just now" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return "edited " + formatter.localizedString(for: date, relativeTo: now)
    }

    static func parse(_ iso: String) -> Date? {
        if let date = parseMWDate(iso) { return date }
        // Some rows carry a naive UTC timestamp (no zone suffix).
        let naive = DateFormatter()
        naive.locale = Locale(identifier: "en_US_POSIX")
        naive.timeZone = TimeZone(identifier: "UTC")
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            naive.dateFormat = format
            if let date = naive.date(from: iso) { return date }
        }
        return nil
    }
}
