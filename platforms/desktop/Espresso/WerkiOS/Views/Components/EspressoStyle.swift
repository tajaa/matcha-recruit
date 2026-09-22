import SwiftUI

/// Warm accents on neutral glass; semantic text stays legible in both appearances.
enum EspressoStyle {
    static let accent = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.91, green: 0.78, blue: 0.61, alpha: 1)
        : UIColor(red: 0.40, green: 0.30, blue: 0.21, alpha: 1) })
    static let canvas = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.055, green: 0.065, blue: 0.085, alpha: 1)
        : UIColor(red: 0.94, green: 0.945, blue: 0.96, alpha: 1) })
    static let card = Color(uiColor: .secondarySystemGroupedBackground)
    // An opaque color avoids multiplying the native placeholder's opacity with
    // hierarchical `.secondary` styling on a translucent field.
    static let placeholder = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.68, green: 0.69, blue: 0.73, alpha: 1)
        : UIColor(red: 0.40, green: 0.41, blue: 0.45, alpha: 1) })
    static let onAccent = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.19, green: 0.14, blue: 0.11, alpha: 1) : .white })
    static let sage = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.65, green: 0.77, blue: 0.61, alpha: 1)
        : UIColor(red: 0.29, green: 0.40, blue: 0.28, alpha: 1) })
    static let urgent = Color(uiColor: UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 1.0, green: 0.46, blue: 0.43, alpha: 1)
        : UIColor(red: 0.68, green: 0.16, blue: 0.13, alpha: 1) })
    static func priority(_ value: String) -> Color {
        switch value {
        case "critical", "high": return urgent
        case "low": return sage
        default: return accent
        }
    }

    /// Accessibility environment values are read-only. These Debug-only overrides
    /// exercise our custom surfaces without changing the simulator's preferences.
    static func previewFlag(_ flag: String) -> Bool {
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        return arguments.contains("-espresso-preview") && arguments.contains(flag)
        #else
        return false
        #endif
    }
}

/// Static, diffused light gives materials depth without motion or bitmap assets.
struct EspressoBackdrop: View {
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                EspressoStyle.canvas
                if !reduceTransparency && contrast != .increased && !EspressoStyle.previewFlag("-opaque") && !EspressoStyle.previewFlag("-contrast") {
                    RadialGradient(colors: [Color(red: 0.86, green: 0.69, blue: 0.50).opacity(scheme == .dark ? 0.16 : 0.32), .clear],
                        center: .topLeading, startRadius: 0, endRadius: geometry.size.width * 1.15)
                    RadialGradient(colors: [Color(red: 0.49, green: 0.66, blue: 0.91).opacity(scheme == .dark ? 0.20 : 0.30), .clear],
                        center: .init(x: 1, y: 0.35), startRadius: 0, endRadius: geometry.size.width * 0.95)
                    RadialGradient(colors: [Color(red: 0.75, green: 0.65, blue: 0.85).opacity(scheme == .dark ? 0.12 : 0.22), .clear],
                        center: .bottomLeading, startRadius: 0, endRadius: geometry.size.width)
                }
            }
        }.ignoresSafeArea().allowsHitTesting(false).accessibilityHidden(true)
    }
}

/// Content sits on frosted material; Liquid Glass is reserved for controls.
struct EspressoSurface: ViewModifier {
    var cornerRadius: CGFloat = 26
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    private var highContrast: Bool { contrast == .increased || EspressoStyle.previewFlag("-contrast") }
    private var opaque: Bool { reduceTransparency || highContrast || EspressoStyle.previewFlag("-opaque") }
    private var shape: RoundedRectangle { RoundedRectangle(cornerRadius: cornerRadius, style: .continuous) }

    func body(content: Content) -> some View {
        content
            .background {
                if opaque { shape.fill(EspressoStyle.card) }
                else {
                    shape.fill(.regularMaterial)
                    shape.fill(.white.opacity(scheme == .dark ? 0.025 : 0.24))
                }
            }
            .overlay {
                shape.strokeBorder(LinearGradient(colors: [
                    .white.opacity(scheme == .dark ? 0.19 : 0.88),
                    .white.opacity(scheme == .dark ? 0.04 : 0.20),
                    .white.opacity(scheme == .dark ? 0.09 : 0.50)
                ], startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 0.75)
                    .allowsHitTesting(false)
                if highContrast {
                    shape.strokeBorder(.primary.opacity(0.45), lineWidth: 1).allowsHitTesting(false)
                }
            }
            .shadow(color: .black.opacity(opaque ? 0 : (scheme == .dark ? 0.12 : 0.035)), radius: 16, x: 0, y: 8)
    }
}

private struct EspressoGlass: ViewModifier {
    var selected: Bool
    var cornerRadius: CGFloat
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var shape: RoundedRectangle { RoundedRectangle(cornerRadius: cornerRadius, style: .continuous) }
    private var highContrast: Bool { contrast == .increased || EspressoStyle.previewFlag("-contrast") }

    @ViewBuilder func body(content: Content) -> some View {
        if reduceTransparency || highContrast || EspressoStyle.previewFlag("-opaque") {
            content.background(selected ? EspressoStyle.accent : EspressoStyle.card, in: shape)
                .foregroundStyle(selected ? EspressoStyle.onAccent : Color.primary)
                .overlay(shape.strokeBorder(.primary.opacity(highContrast ? 0.45 : 0.08)).allowsHitTesting(false))
        } else {
            // Compile on Xcode 16 as well as Xcode 26; the minimum OS remains iOS 17.
            #if compiler(>=6.2)
            if #available(iOS 26.0, *) {
                content.foregroundStyle(selected ? EspressoStyle.accent : Color.primary)
                    .glassEffect(.regular.tint(selected ? EspressoStyle.accent.opacity(0.18) : nil).interactive(!reduceMotion && !EspressoStyle.previewFlag("-reduce-motion")), in: shape)
            } else { fallback(content) }
            #else
            fallback(content)
            #endif
        }
    }

    private func fallback(_ content: Content) -> some View {
        content.foregroundStyle(selected ? EspressoStyle.accent : Color.primary)
            .background(selected ? EspressoStyle.accent.opacity(0.12) : .clear, in: shape)
            .modifier(EspressoSurface(cornerRadius: cornerRadius))
    }
}

struct EspressoGlassGroup<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) { GlassEffectContainer(spacing: 6) { content } }
        else { content }
        #else
        content
        #endif
    }
}

struct EspressoCard: ViewModifier {
    func body(content: Content) -> some View {
        content.padding(20).modifier(EspressoSurface())
    }
}

struct EspressoPressStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var motionDisabled: Bool { reduceMotion || EspressoStyle.previewFlag("-reduce-motion") }
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.86 : 1)
            .scaleEffect(configuration.isPressed && !motionDisabled ? 0.985 : 1)
            .animation(motionDisabled ? nil : .easeOut(duration: 0.16), value: configuration.isPressed)
    }
}

extension View {
    func espressoCard() -> some View { modifier(EspressoCard()) }
    func espressoSurface(cornerRadius: CGFloat = 26) -> some View { modifier(EspressoSurface(cornerRadius: cornerRadius)) }
    func espressoBackground() -> some View { background { EspressoBackdrop() } }
    func espressoGlass(selected: Bool = false, cornerRadius: CGFloat = 100) -> some View {
        modifier(EspressoGlass(selected: selected, cornerRadius: cornerRadius))
    }
    func espressoError(_ message: Binding<String?>) -> some View {
        alert("Couldn't complete that", isPresented: Binding(
            get: { message.wrappedValue != nil },
            set: { if !$0 { message.wrappedValue = nil } }
        )) { Button("OK", role: .cancel) { message.wrappedValue = nil } }
        message: { Text(message.wrappedValue ?? "Please try again.") }
    }
}

struct EspressoProjectGlyph: View {
    let symbol: String
    var color: Color = EspressoStyle.accent
    var body: some View {
        Image(systemName: symbol).font(.system(size: 22, weight: .medium)).symbolRenderingMode(.hierarchical)
            .foregroundStyle(color).frame(width: 48, height: 48)
            .background(LinearGradient(colors: [color.opacity(0.17), color.opacity(0.04)],
                startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(color.opacity(0.12), lineWidth: 0.5))
            .accessibilityHidden(true)
    }
}

struct EspressoBadge: View {
    let text: String
    var color: Color = EspressoStyle.accent
    var body: some View {
        Text(text).font(.caption.weight(.semibold))
            .foregroundStyle(color).padding(.horizontal, 10).padding(.vertical, 5)
            .background(color.opacity(0.10), in: Capsule())
    }
}

struct EspressoSectionHeading: View {
    let title: String
    var detail: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.title3.weight(.semibold))
            Spacer()
            if let detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

struct EspressoEmptyState: View {
    let title: String
    let message: String
    let symbol: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 30, weight: .light))
                .foregroundStyle(EspressoStyle.accent).padding(18)
                .background(EspressoStyle.accent.opacity(0.08), in: Circle())
            Text(title).font(.title3.weight(.semibold))
            Text(message).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity).padding(.vertical, 32).padding(.horizontal, 20)
    }
}
