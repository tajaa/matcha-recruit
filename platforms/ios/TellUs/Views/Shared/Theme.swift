import SwiftUI

/// Beetlejuse visual language: near-black ground, a single amber accent, and
/// surfaces that are quiet by default. Dark-only by design.
enum TU {
    // Ground is faintly blue-shifted so the warm amber reads hotter against it.
    static let ink = Color(red: 0.027, green: 0.027, blue: 0.039)       // #07070A
    static let inkRaised = Color(red: 0.063, green: 0.063, blue: 0.082) // #101015

    static let ember = Color(red: 0.910, green: 0.541, blue: 0.180)     // #E88A2E — brand accent
    static let emberHot = Color(red: 1.000, green: 0.714, blue: 0.361)  // #FFB65C — highlight
    static let emberDeep = Color(red: 0.706, green: 0.322, blue: 0.102) // #B4521A — gradient tail

    static let textDim = Color(red: 0.604, green: 0.604, blue: 0.647)   // #9A9AA5

    /// Hairline that separates a surface from the ground without drawing a box
    /// around it.
    static let hairline = Color.white.opacity(0.10)

    /// Surface fill. An explicit translucent white rather than a material —
    /// `.ultraThinMaterial` over near-black just resolves to flat gray.
    static let surface = Color.white.opacity(0.05)

    /// Utility/label face. Mono because most of what it labels is data — it
    /// also keeps ledger columns from dancing as amounts change.
    static func eyebrow(_ size: CGFloat = 11) -> Font {
        .system(size: size, weight: .medium, design: .monospaced)
    }
}

// MARK: - Ambient ground

/// Ink with one soft ember pool behind the top of the screen.
///
/// Layout note: the glow lives in an `.overlay` on a fill that takes whatever
/// it's offered, so this view never reports the glow's intrinsic size. A
/// `ZStack` of oversized circles reports the *largest child's* width, which
/// pushes sibling content wider than the screen.
struct EmberBackground: View {
    var body: some View {
        TU.ink
            .overlay(alignment: .top) {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [TU.ember.opacity(0.30), TU.ember.opacity(0.06), .clear],
                            center: .center, startRadius: 0, endRadius: 300
                        )
                    )
                    .frame(width: 600, height: 600)
                    .offset(y: -260)
                    .blur(radius: 40)
            }
            .clipped()
            .ignoresSafeArea()
    }
}

// MARK: - Typeface

/// Inter (variable font, bundled as Resources/Fonts/Inter.ttf, PostScript
/// name "Inter-Regular") replaces the system font everywhere. It's a
/// variable font — `.weight(_:)`/`.bold()` chained onto these adjust the
/// wght axis directly rather than substituting a static face, which is why
/// every token below is declared at the Regular instance.
extension Font {
    static func inter(_ size: CGFloat, relativeTo style: Font.TextStyle) -> Font {
        .custom("Inter-Regular", size: size, relativeTo: style)
    }

    static var interLargeTitle: Font { inter(34, relativeTo: .largeTitle) }
    static var interTitle: Font { inter(28, relativeTo: .title) }
    static var interTitle2: Font { inter(22, relativeTo: .title2) }
    static var interTitle3: Font { inter(20, relativeTo: .title3) }
    static var interHeadline: Font { inter(17, relativeTo: .headline).weight(.semibold) }
    static var interBody: Font { inter(17, relativeTo: .body) }
    static var interSubheadline: Font { inter(15, relativeTo: .subheadline) }
    static var interFootnote: Font { inter(13, relativeTo: .footnote) }
    static var interCaption: Font { inter(12, relativeTo: .caption) }
    static var interCaption2: Font { inter(11, relativeTo: .caption2) }
}

// MARK: - Themed screens

/// One-line retrofit for a List/ScrollView/Form screen: drops `EmberBackground`
/// behind the content and clears the system chrome that would otherwise paint
/// over it. Attach to the scroll view itself, not a wrapping VStack —
/// `.scrollContentBackground(.hidden)` only affects the view it's called on.
struct ThemedScreen: ViewModifier {
    func body(content: Content) -> some View {
        content
            .scrollContentBackground(.hidden)
            .background(EmberBackground())
            .toolbarBackground(.hidden, for: .navigationBar)
    }
}

extension View {
    func themedScreen() -> some View { modifier(ThemedScreen()) }

    /// Same background/chrome for a non-scrolling container hosting a
    /// segmented Picker + a switched child List/ScrollView — no
    /// `.scrollContentBackground` here since there's no scroll view at this
    /// level; the child still needs its own `.scrollContentBackground(.hidden)`.
    func themedContainer() -> some View {
        self.background(EmberBackground()).toolbarBackground(.hidden, for: .navigationBar)
    }

    /// List row treatment — dark slab fill, keeps swipeActions/onDelete intact.
    func themedRow() -> some View { self.listRowBackground(TU.inkRaised) }
}

// MARK: - Brand mark

/// The app mark — shared by the splash and the login header so
/// session-restore doesn't flash a different visual language.
struct BrandMark: View {
    var size: CGFloat = 44

    var body: some View {
        Image(systemName: "bubble.left.and.bubble.right.fill")
            .font(.system(size: size, weight: .medium))
            .foregroundStyle(TU.ember)
    }
}

// MARK: - Surfaces

struct GlassCard: ViewModifier {
    var radius: CGFloat = 18
    var strokeOpacity: Double = 1

    func body(content: Content) -> some View {
        content
            .background(TU.surface, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(TU.hairline, lineWidth: 1)
                    .opacity(strokeOpacity)
            )
    }
}

extension View {
    func glassCard(radius: CGFloat = 18, strokeOpacity: Double = 1) -> some View {
        modifier(GlassCard(radius: radius, strokeOpacity: strokeOpacity))
    }
}

/// A plain text field. Focus lights the border amber rather than moving or
/// resizing anything, so the field stays put while the keyboard rises.
struct GlassField<Content: View>: View {
    var icon: String? = nil
    var isFocused: Bool = false
    @ViewBuilder var content: Content

    var body: some View {
        HStack(spacing: 10) {
            if let icon {
                Image(systemName: icon)
                    .font(.custom("Inter-Regular", size: 14).weight(.medium))
                    .foregroundStyle(isFocused ? TU.ember : TU.textDim)
                    .frame(width: 18)
            }
            content
                .font(.custom("Inter-Regular", size: 16))
                .foregroundStyle(.white)
                .tint(TU.ember)
        }
        .padding(.horizontal, 16)
        .frame(height: 52)
        .background(TU.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(isFocused ? TU.ember : TU.hairline, lineWidth: 1)
        )
        .animation(.easeOut(duration: 0.18), value: isFocused)
    }
}

/// Primary action — the one saturated element on a screen.
struct EmberButtonStyle: ButtonStyle {
    var enabled: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.custom("Inter-Regular", size: 16).weight(.semibold))
            .foregroundStyle(enabled ? TU.ink : TU.textDim)
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(enabled ? TU.ember : TU.surface)
            )
            .opacity(configuration.isPressed ? 0.82 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// Quiet secondary action — outline only, for the path not being pushed.
struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.custom("Inter-Regular", size: 16).weight(.medium))
            .foregroundStyle(.white.opacity(0.92))
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(TU.hairline, lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.7 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

// MARK: - Ember ring

/// Level progress as a burning arc: cold track, hot leading tip. The product
/// already talks about streaks in flames, so progress reads as heat you keep
/// alive rather than a bar you fill.
struct EmberRing: View {
    let progress: Double        // 0…1
    var lineWidth: CGFloat = 10
    var size: CGFloat = 190

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown: Double = 0

    private var clamped: Double { min(max(progress, 0), 1) }

    var body: some View {
        ZStack {
            Circle()
                .stroke(.white.opacity(0.07), lineWidth: lineWidth)

            Circle()
                .trim(from: 0, to: shown)
                .stroke(
                    AngularGradient(
                        colors: [TU.emberDeep, TU.ember, TU.emberHot],
                        center: .center,
                        startAngle: .degrees(0),
                        endAngle: .degrees(360 * max(clamped, 0.001))
                    ),
                    style: StrokeStyle(lineWidth: lineWidth, lineCap: .round)
                )
        }
        .rotationEffect(.degrees(-90))   // start the burn at 12 o'clock
        .frame(width: size, height: size)
        .onAppear {
            guard !reduceMotion else { shown = clamped; return }
            withAnimation(.easeOut(duration: 1.0).delay(0.1)) { shown = clamped }
        }
        .onChange(of: clamped) { _, new in
            withAnimation(.easeOut(duration: 0.6)) { shown = new }
        }
    }
}

// MARK: - Divider

/// Hairline / "OR" / hairline row separating password auth from Google
/// sign-in — shared by LoginView and SignupView so the two screens stay
/// visually identical.
struct OrDivider: View {
    var body: some View {
        HStack(spacing: 12) {
            Rectangle().fill(TU.hairline).frame(height: 1)
            Text("OR")
                .font(TU.eyebrow())
                .foregroundStyle(TU.textDim)
            Rectangle().fill(TU.hairline).frame(height: 1)
        }
    }
}

// MARK: - Entrance

/// One quiet load sequence per screen — elements fade in in reading order.
struct RiseIn: ViewModifier {
    let index: Double
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 8)
            .onAppear {
                guard !reduceMotion else { shown = true; return }
                withAnimation(.easeOut(duration: 0.4).delay(0.05 * index)) { shown = true }
            }
    }
}

extension View {
    func riseIn(_ index: Double) -> some View { modifier(RiseIn(index: index)) }
}
