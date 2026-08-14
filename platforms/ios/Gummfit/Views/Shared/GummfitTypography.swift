import SwiftUI

enum GummfitTypography {
    static let pageTitle = Font.system(.title2, design: .default).weight(.semibold)
    static let sectionTitle = Font.system(.headline, design: .default).weight(.semibold)
    static let body = Font.system(.body, design: .default)
    static let label = Font.system(.subheadline, design: .default).weight(.medium)
    static let subtitle = Font.system(.subheadline, design: .default)
    static let muted = Font.system(.footnote, design: .default)
    static let caption = Font.system(.caption, design: .default)
    static let status = Font.system(.caption2, design: .default).weight(.semibold)
}

extension View {
    func gummfitPageTitle() -> some View {
        font(GummfitTypography.pageTitle).foregroundStyle(GummfitTheme.textPrimary)
    }

    func gummfitSectionTitle() -> some View {
        font(GummfitTypography.sectionTitle).foregroundStyle(GummfitTheme.textPrimary)
    }

    func gummfitSubtitle() -> some View {
        font(GummfitTypography.subtitle).foregroundStyle(GummfitTheme.textDim)
    }

    func gummfitMuted() -> some View {
        font(GummfitTypography.muted).foregroundStyle(GummfitTheme.muted)
    }
}
