import SwiftUI

extension Color {
    init(hex: String) {
        let value = UInt64(hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")), radix: 16) ?? 0
        self.init(
            red: Double((value >> 16) & 0xff) / 255,
            green: Double((value >> 8) & 0xff) / 255,
            blue: Double(value & 0xff) / 255
        )
    }
}

/// Shared design tokens for the operator app. The hex values mirror the
/// Cappe dashboard's Tailwind zinc/emerald palette in client/src/cappe.
enum GummfitTheme {
    static let canvasHex = "#09090B"
    static let backgroundRaisedHex = "#18181B"
    static let surfaceRaisedHex = "#27272A"
    static let borderHex = "#27272A"
    static let inputBorderHex = "#3F3F46"
    static let textPrimaryHex = "#FAFAFA"
    static let textSecondaryHex = "#D4D4D8"
    static let textDimHex = "#A1A1AA"
    static let mutedHex = "#71717A"
    static let accentHex = "#10B981"
    static let accentHoverHex = "#34D399"
    static let accentDeepHex = "#047857"
    static let warningHex = "#FBBF24"
    static let infoHex = "#38BDF8"
    static let dangerHex = "#F87171"

    static let background = Color(hex: canvasHex)
    static let backgroundRaised = Color(hex: backgroundRaisedHex)
    static let surface = Color(hex: backgroundRaisedHex)
    static let surfaceRaised = Color(hex: surfaceRaisedHex)
    static let border = Color(hex: borderHex)
    static let inputBorder = Color(hex: inputBorderHex)
    static let textPrimary = Color(hex: textPrimaryHex)
    static let textSecondary = Color(hex: textSecondaryHex)
    static let textDim = Color(hex: textDimHex)
    static let muted = Color(hex: mutedHex)
    static let accent = Color(hex: accentHex)
    static let accentHover = Color(hex: accentHoverHex)
    static let accentDeep = Color(hex: accentDeepHex)
    static let warning = Color(hex: warningHex)
    static let info = Color(hex: infoHex)
    static let danger = Color(hex: dangerHex)

    static let controlRadius: CGFloat = 8
    static let cardRadius: CGFloat = 12
    static let pillRadius: CGFloat = 999

    static var pageBackground: LinearGradient {
        LinearGradient(
            colors: [backgroundRaised, background],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

enum GummfitSpacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 20
    static let xxl: CGFloat = 24
    static let xxxl: CGFloat = 32
}

struct GummfitCard: ViewModifier {
    var padding: CGFloat = GummfitSpacing.lg

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(GummfitTheme.surface, in: RoundedRectangle(cornerRadius: GummfitTheme.cardRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GummfitTheme.cardRadius, style: .continuous)
                    .stroke(GummfitTheme.border, lineWidth: 1)
            }
    }
}

extension View {
    func gummfitCard(padding: CGFloat = 18) -> some View {
        modifier(GummfitCard(padding: padding))
    }

    /// Applies the owner-app navigation treatment. Keeping this on screen
    /// roots makes every title readable and prevents UIKit's default toolbar
    /// material from turning the header nearly black.
    func gummfitScreenChrome() -> some View {
        background(GummfitTheme.pageBackground.ignoresSafeArea())
            .toolbarBackground(GummfitTheme.backgroundRaised, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
    }

    func gummfitListBackground() -> some View {
        scrollContentBackground(.hidden)
            .background(GummfitTheme.pageBackground.ignoresSafeArea())
    }

    func gummfitListRow() -> some View {
        listRowBackground(GummfitTheme.surface)
            .listRowSeparatorTint(GummfitTheme.border)
            .listRowInsets(EdgeInsets(top: GummfitSpacing.md, leading: GummfitSpacing.xl, bottom: GummfitSpacing.md, trailing: GummfitSpacing.xl))
    }
}
