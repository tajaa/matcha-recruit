import SwiftUI

private struct GummfitFilledButtonStyle: ButtonStyle {
    let background: Color
    let foreground: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(GummfitTypography.label)
            .foregroundStyle(foreground)
            .padding(.horizontal, GummfitSpacing.lg)
            .padding(.vertical, GummfitSpacing.md)
            .background(background.opacity(configuration.isPressed ? 0.78 : 1), in: RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

struct GummfitPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        GummfitFilledButtonStyle(background: GummfitTheme.accent, foreground: GummfitTheme.background)
            .makeBody(configuration: configuration)
    }
}

struct GummfitDestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        GummfitFilledButtonStyle(background: GummfitTheme.danger, foreground: GummfitTheme.background)
            .makeBody(configuration: configuration)
    }
}

struct GummfitSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(GummfitTypography.label)
            .foregroundStyle(GummfitTheme.textPrimary)
            .padding(.horizontal, GummfitSpacing.lg)
            .padding(.vertical, GummfitSpacing.md)
            .background(GummfitTheme.surfaceRaised.opacity(configuration.isPressed ? 0.7 : 1), in: RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous)
                    .stroke(GummfitTheme.inputBorder, lineWidth: 1)
            }
    }
}

struct GummfitGhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(GummfitTypography.label)
            .foregroundStyle(configuration.isPressed ? GummfitTheme.accentHover : GummfitTheme.textSecondary)
            .padding(.horizontal, GummfitSpacing.sm)
            .padding(.vertical, GummfitSpacing.sm)
    }
}

extension ButtonStyle where Self == GummfitPrimaryButtonStyle {
    static var gummfitPrimary: Self { Self() }
}

extension ButtonStyle where Self == GummfitSecondaryButtonStyle {
    static var gummfitSecondary: Self { Self() }
}

extension ButtonStyle where Self == GummfitGhostButtonStyle {
    static var gummfitGhost: Self { Self() }
}

extension ButtonStyle where Self == GummfitDestructiveButtonStyle {
    static var gummfitDestructive: Self { Self() }
}

extension View {
    func gummfitFullWidth() -> some View {
        frame(maxWidth: .infinity)
    }
}
