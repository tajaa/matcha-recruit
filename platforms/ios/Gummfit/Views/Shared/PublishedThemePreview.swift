import SwiftUI

struct CappePublishedThemePreview: View {
    let preset: CappePublishedThemePreset

    private var background: Color { Color(hex: preset.swatch.background) }
    private var surface: Color { Color(hex: preset.swatch.surface) }
    private var brand: Color { Color(hex: preset.swatch.brand) }
    private var text: Color { Color(hex: preset.swatch.text) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("YOUR BRAND")
                    .font(.caption.weight(.bold))
                    .tracking(1.2)
                Spacer()
                Image(systemName: "line.3.horizontal")
            }
            .foregroundStyle(text)
            .padding(.horizontal, GummfitSpacing.xl)
            .padding(.vertical, GummfitSpacing.lg)

            VStack(alignment: .leading, spacing: GummfitSpacing.lg) {
                Text(preset.name)
                    .font(.system(.largeTitle, design: preset.headingFont == "Inter" ? .default : .serif).weight(.bold))
                    .foregroundStyle(text)
                Text(preset.blurb)
                    .font(.body)
                    .foregroundStyle(text.opacity(0.72))
                Button("Explore") {}
                    .buttonStyle(PublishedPreviewButtonStyle(background: brand, foreground: Color(hex: preset.swatch.text)))
            }
            .padding(.horizontal, GummfitSpacing.xl)
            .padding(.vertical, GummfitSpacing.xxxl)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(surface)

            HStack(spacing: GummfitSpacing.md) {
                RoundedRectangle(cornerRadius: 5)
                    .fill(brand)
                    .frame(width: 44, height: 44)
                VStack(alignment: .leading, spacing: GummfitSpacing.xs) {
                    Text("A considered detail")
                        .font(.headline)
                        .foregroundStyle(text)
                    Text("Preview only; editing stays on web.")
                        .font(.caption)
                        .foregroundStyle(text.opacity(0.65))
                }
            }
            .padding(GummfitSpacing.xl)
        }
        .background(background)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(text.opacity(0.15), lineWidth: 1)
        }
        .padding()
        .navigationTitle("Theme preview")
    }
}

private struct PublishedPreviewButtonStyle: ButtonStyle {
    let background: Color
    let foreground: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(foreground)
            .padding(.horizontal, 18)
            .padding(.vertical, 10)
            .background(background.opacity(configuration.isPressed ? 0.75 : 1), in: Capsule())
    }
}
