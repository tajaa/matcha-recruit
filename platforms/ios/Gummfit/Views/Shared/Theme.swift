import SwiftUI

/// Shared design tokens for the operator app. These are deliberately explicit
/// colors rather than adaptive materials: the dashboard must retain its
/// hierarchy in both light and dark system appearances.
enum GummfitTheme {
    static let accent = Color(red: 0.20, green: 0.85, blue: 0.44)
    static let accentDeep = Color(red: 0.05, green: 0.42, blue: 0.22)
    static let background = Color(red: 0.035, green: 0.071, blue: 0.075)
    static let backgroundRaised = Color(red: 0.055, green: 0.106, blue: 0.110)
    static let surface = Color(red: 0.078, green: 0.137, blue: 0.141)
    static let surfaceRaised = Color(red: 0.102, green: 0.173, blue: 0.176)
    static let border = Color.white.opacity(0.11)
    static let textPrimary = Color.white
    static let textDim = Color(red: 0.62, green: 0.69, blue: 0.69)
    static let warning = Color(red: 1.0, green: 0.72, blue: 0.20)

    static let cardRadius: CGFloat = 22

    static var pageBackground: LinearGradient {
        LinearGradient(
            colors: [backgroundRaised, background],
            startPoint: .top,
            endPoint: .bottom
        )
    }
}

struct GummfitCard: ViewModifier {
    var padding: CGFloat = 18

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
            .listRowInsets(EdgeInsets(top: 13, leading: 20, bottom: 13, trailing: 20))
    }
}
