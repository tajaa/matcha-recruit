import SwiftUI
import AppKit
import CoreText

/// Ticket-local type: bundled Inter, with a system fallback for missing resources.
/// Registration is process-scoped and happens once, including in previews.
enum TicketTypography {
    private static let registered: Bool = {
        guard let url = Bundle.main.url(forResource: "Inter", withExtension: "ttf", subdirectory: "Fonts") else {
            return false
        }
        CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        return NSFont(name: "Inter-Regular", size: 13) != nil
    }()

    static func native(size: CGFloat) -> NSFont {
        if registered, let font = NSFont(name: "Inter-Regular", size: size) { return font }
        return .systemFont(ofSize: size)
    }

    static func font(size: CGFloat, weight: Font.Weight) -> Font {
        registered
            ? .custom("Inter-Regular", fixedSize: size).weight(weight)
            : .system(size: size, weight: weight)
    }
}

extension Font {
    static func ticket(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        TicketTypography.font(size: size, weight: weight)
    }

    /// App-wide alias used by the sidebar and board surfaces that frame tickets.
    static func espresso(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        TicketTypography.font(size: size, weight: weight)
    }
}

/// Quiet labels share one baseline; hierarchy comes from space, not weight or boxes.
struct TicketSectionHeading: View {
    let title: String
    var detail: String? = nil

    var body: some View {
        HStack(spacing: 8) {
            Text(title)
            if let detail { Text(detail) }
            Spacer(minLength: 0)
        }
        .font(.ticket(size: 11))
        .foregroundStyle(.secondary)
    }
}

/// Render brief headings without bold chrome or changing the stored Markdown.
struct TicketBriefText: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(text.components(separatedBy: "\n\n").enumerated()), id: \.offset) { _, block in
                let lines = block.components(separatedBy: "\n")
                let first = lines.first ?? ""
                let hashes = first.prefix(while: { $0 == "#" }).count
                if (1...6).contains(hashes), first.dropFirst(hashes).hasPrefix(" ") {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(String(first.dropFirst(hashes + 1)))
                            .font(.ticket(size: 11))
                            .foregroundStyle(.secondary)
                        if lines.count > 1 { Text(lines.dropFirst().joined(separator: "\n")) }
                    }
                } else {
                    Text(block)
                }
            }
        }
        .font(.ticket(size: 13))
        .lineSpacing(3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
    }
}
