import SwiftUI

enum GummfitStatusTone {
    case success
    case warning
    case info
    case danger
    case neutral

    var foreground: Color {
        switch self {
        case .success: GummfitTheme.accentHover
        case .warning: GummfitTheme.warning
        case .info: GummfitTheme.info
        case .danger: GummfitTheme.danger
        case .neutral: GummfitTheme.textDim
        }
    }

    var background: Color { foreground.opacity(0.15) }
}

struct GummfitStatusPill: View {
    let status: String
    var label: String?

    private var normalizedStatus: String { status.lowercased() }

    private var tone: GummfitStatusTone {
        switch normalizedStatus {
        case "published", "active", "paid", "confirmed", "subscribed", "sent", "approved", "verified": .success
        case "pending", "scheduled", "negotiating", "submitted", "due", "processing", "pending_review": .warning
        case "fulfilled", "accepted", "completed": .info
        case "bounced", "failed", "rejected", "suspended", "flagged": .danger
        default: .neutral
        }
    }

    private var displayLabel: String {
        label ?? status.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var body: some View {
        Text(displayLabel)
            .font(GummfitTypography.status)
            .textCase(.uppercase)
            .foregroundStyle(tone.foreground)
            .padding(.horizontal, GummfitSpacing.sm)
            .padding(.vertical, GummfitSpacing.xs)
            .background(tone.background, in: Capsule())
            .accessibilityLabel("Status: \(displayLabel)")
    }
}
