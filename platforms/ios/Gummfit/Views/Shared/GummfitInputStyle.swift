import SwiftUI

struct GummfitTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(GummfitTypography.body)
            .foregroundStyle(GummfitTheme.textPrimary)
            .padding(.horizontal, GummfitSpacing.md)
            .padding(.vertical, GummfitSpacing.md)
            .background(GummfitTheme.surface, in: RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous)
                    .stroke(GummfitTheme.inputBorder, lineWidth: 1)
            }
    }
}

private struct GummfitInputModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(GummfitTypography.body)
            .foregroundStyle(GummfitTheme.textPrimary)
            .padding(.horizontal, GummfitSpacing.md)
            .padding(.vertical, GummfitSpacing.md)
            .background(GummfitTheme.surface, in: RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: GummfitTheme.controlRadius, style: .continuous)
                    .stroke(GummfitTheme.inputBorder, lineWidth: 1)
            }
    }
}

struct GummfitFieldLabel: View {
    let text: String

    var body: some View {
        Text(text)
            .font(GummfitTypography.label)
            .foregroundStyle(GummfitTheme.textSecondary)
    }
}

extension View {
    func gummfitInput() -> some View {
        modifier(GummfitInputModifier())
    }
}
