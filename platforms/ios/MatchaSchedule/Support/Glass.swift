import SwiftUI

// MARK: - Surfaces
//
// Two kinds of glass, on purpose. Content cards are frosted material with a
// specular edge and a two-layer shadow for depth. Floating controls (the week
// pill, segmented control, secondary buttons) use the system's Liquid Glass on
// iOS 26, which Apple reserves for the control layer, and the same frosted
// treatment before it. Reduce Transparency gets opaque fills everywhere.

struct GlassSurface: ViewModifier {
    var cornerRadius: CGFloat = Metrics.cardRadius
    var tint: Color?
    var elevated = true
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                ZStack {
                    if reduceTransparency {
                        shape.fill(Palette.surfaceSolid)
                    } else {
                        shape.fill(.ultraThinMaterial)
                        shape.fill(Color.white.opacity(scheme == .dark ? 0.03 : 0.28))
                    }
                    if let tint {
                        shape.fill(LinearGradient(
                            colors: [tint.opacity(scheme == .dark ? 0.28 : 0.20), tint.opacity(0.02)],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        ))
                    }
                }
            }
            .overlay {
                shape.strokeBorder(
                    LinearGradient(
                        colors: [Color.white.opacity(scheme == .dark ? 0.22 : 0.85),
                                 Color.white.opacity(scheme == .dark ? 0.04 : 0.15)],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
            }
            .shadow(color: Palette.shadow.opacity(elevated ? (scheme == .dark ? 0.45 : 0.10) : 0), radius: 22, y: 12)
            .shadow(color: Palette.shadow.opacity(elevated ? 0.06 : 0), radius: 2, y: 1)
    }
}

extension View {
    func glassSurface(cornerRadius: CGFloat = Metrics.cardRadius, tint: Color? = nil, elevated: Bool = true) -> some View {
        modifier(GlassSurface(cornerRadius: cornerRadius, tint: tint, elevated: elevated))
    }

    /// Liquid Glass on iOS 26; frosted material before it.
    ///
    /// `glassEffect` only exists in the iOS 26 SDK. `#available` is a runtime
    /// check and does not stop an older SDK failing to compile the call, so
    /// the compiler check keeps Xcode 16 builds (CI's macos-15 image) working;
    /// they always take the material path.
    @ViewBuilder
    func glassControl<S: Shape>(in shape: S, interactive: Bool = true) -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.glassEffect(interactive ? .regular.interactive() : .regular, in: shape)
        } else {
            materialControl(in: shape)
        }
        #else
        materialControl(in: shape)
        #endif
    }

    private func materialControl<S: Shape>(in shape: S) -> some View {
        self.background(.ultraThinMaterial, in: shape)
            .overlay(shape.stroke(Color.white.opacity(0.55), lineWidth: 0.8))
            .shadow(color: Palette.shadow.opacity(0.10), radius: 12, y: 6)
    }

    /// The ambient light behind a whole screen.
    func ambientBackground(_ tone: DayPart? = nil) -> some View {
        background { AmbientBackground(tone: tone).ignoresSafeArea() }
    }

    /// Staggered fade-up on first appearance. Reduce Motion gets a plain fade.
    func rise(delay: Double = 0) -> some View {
        modifier(Rise(delay: delay))
    }
}

private struct Rise: ViewModifier {
    let delay: Double
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown || reduceMotion ? 0 : 14)
            .onAppear {
                withAnimation(.spring(response: 0.55, dampingFraction: 0.86).delay(delay)) { shown = true }
            }
    }
}

// MARK: - Ambient background
//
// A slow-drifting mesh of foam and leaf, with one corner lit by the day part
// of the employee's next shift. Static under Reduce Motion.

struct AmbientBackground: View {
    var tone: DayPart?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme
    @Environment(\.scenePhase) private var scenePhase
    /// Off while a pushed screen covers this one, so only the visible
    /// background animates. (A sheet does not hide its presenter; the drift is
    /// slow enough that 12 fps is plenty for the one or two left running.)
    @State private var onScreen = false

    private var animating: Bool { onScreen && !reduceMotion && scenePhase == .active }

    var body: some View {
        ZStack {
            Palette.foam
            if #available(iOS 18.0, *) {
                TimelineView(.animation(minimumInterval: 1.0 / 12, paused: !animating)) { context in
                    MeshGradient(
                        width: 3, height: 3,
                        points: points(at: reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate),
                        colors: colors
                    )
                }
            } else {
                GeometryReader { proxy in
                    let size = proxy.size
                    ZStack {
                        Circle().fill(toneColor.opacity(scheme == .dark ? 0.35 : 0.45))
                            .frame(width: size.width * 1.1).offset(x: size.width * 0.45, y: -size.height * 0.35)
                        Circle().fill(Palette.sprout.opacity(scheme == .dark ? 0.18 : 0.35))
                            .frame(width: size.width).offset(x: -size.width * 0.45, y: size.height * 0.1)
                        Circle().fill(Palette.dusk.opacity(scheme == .dark ? 0.20 : 0.18))
                            .frame(width: size.width * 0.9).offset(x: size.width * 0.2, y: size.height * 0.45)
                    }
                    .blur(radius: 90)
                    .frame(width: size.width, height: size.height)
                }
            }
        }
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
    }

    private var toneColor: Color { (tone ?? .mid).color }

    private var colors: [Color] {
        let dark = scheme == .dark
        let foam = Palette.foam
        let lit = toneColor.opacity(dark ? 0.46 : 0.55)
        let leaf = Palette.sprout.opacity(dark ? 0.18 : 0.42)
        let dusk = Palette.dusk.opacity(dark ? 0.26 : 0.22)
        let dawn = Palette.dawn.opacity(dark ? 0.16 : 0.22)
        return [
            leaf, foam.opacity(0.4), lit,
            foam, leaf.opacity(0.6), foam.opacity(0.5),
            dusk, foam.opacity(0.3), dawn,
        ]
    }

    private func points(at time: TimeInterval) -> [SIMD2<Float>] {
        let t = Float(time)
        func drift(_ speed: Float, _ phase: Float, _ amount: Float) -> Float { sin(t * speed + phase) * amount }
        return [
            [0, 0], [0.5 + drift(0.11, 0, 0.08), 0], [1, 0],
            [0, 0.5 + drift(0.09, 1, 0.07)],
            [0.5 + drift(0.07, 2, 0.12), 0.5 + drift(0.08, 3, 0.10)],
            [1, 0.5 + drift(0.10, 4, 0.07)],
            [0, 1], [0.5 + drift(0.12, 5, 0.08), 1], [1, 1],
        ]
    }
}

// MARK: - Buttons

/// The one filled action on a screen: a leaf capsule with a soft glow.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(TypeScale.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 52)
            .padding(.horizontal, 20)
            .background {
                Capsule().fill(Palette.leafGradient)
                    .overlay(Capsule().strokeBorder(Color.white.opacity(0.35), lineWidth: 1).blendMode(.overlay))
            }
            .shadow(color: Palette.leaf.opacity(isEnabled ? 0.38 : 0), radius: 16, y: 8)
            .opacity(isEnabled ? 1 : 0.45)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// Secondary actions: a glass capsule.
struct GlassButtonStyle: ButtonStyle {
    var tint: Color = Palette.ink

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(TypeScale.callout)
            .foregroundStyle(tint)
            .padding(.horizontal, 16).padding(.vertical, 10)
            .glassControl(in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// Whole-card taps: a gentle press-in.
struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .brightness(configuration.isPressed ? -0.02 : 0)
            .animation(.spring(response: 0.28, dampingFraction: 0.75), value: configuration.isPressed)
    }
}

// MARK: - Small pieces

/// Uppercase label above a group: what the group is.
struct Eyebrow: View {
    let text: String
    var color: Color = Palette.inkSoft

    init(_ text: String, color: Color = Palette.inkSoft) {
        self.text = text
        self.color = color
    }

    var body: some View {
        Text(text.uppercased())
            .font(TypeScale.eyebrow)
            .tracking(1.4)
            .foregroundStyle(color)
    }
}

struct SectionTitle: View {
    let title: String
    var trailing: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Eyebrow(title)
            Spacer()
            if let trailing { Text(trailing).font(TypeScale.caption).foregroundStyle(Palette.inkFaint) }
        }
        .padding(.horizontal, 4)
    }
}

struct Avatar: View {
    let name: String
    var size: CGFloat = 44

    private var initials: String {
        let parts = name.split(separator: " ").prefix(2)
        let letters = parts.compactMap(\.first).map(String.init).joined()
        return letters.isEmpty ? "·" : letters.uppercased()
    }

    /// A stable light per person, so a coworker keeps their color.
    private var tone: DayPart {
        let sum = name.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        return [DayPart.opener, .mid, .closer][sum % 3]
    }

    var body: some View {
        Text(initials)
            .font(.inter(size * 0.36, .semibold, relativeTo: .headline))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(Circle().fill(LinearGradient(colors: [tone.color, tone.color.opacity(0.6)],
                                                     startPoint: .topLeading, endPoint: .bottomTrailing)))
            .overlay(Circle().strokeBorder(Color.white.opacity(0.5), lineWidth: 1))
            .shadow(color: tone.color.opacity(0.3), radius: 8, y: 4)
            .accessibilityHidden(true)
    }
}

struct StatusPill: View {
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(text).font(TypeScale.caption)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(color.opacity(0.13), in: Capsule())
        .overlay(Capsule().strokeBorder(color.opacity(0.2), lineWidth: 0.5))
    }
}

/// A segmented control whose thumb slides between options.
struct GlassSegmented<Value: Hashable>: View {
    let options: [(value: Value, label: String)]
    @Binding var selection: Value
    @Namespace private var namespace

    var body: some View {
        HStack(spacing: 4) {
            ForEach(options, id: \.value) { option in
                let selected = option.value == selection
                Button {
                    withAnimation(.spring(response: 0.38, dampingFraction: 0.82)) { selection = option.value }
                } label: {
                    Text(option.label)
                        .font(TypeScale.callout)
                        .foregroundStyle(selected ? Palette.ink : Palette.inkSoft)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 9)
                        .background {
                            if selected {
                                Capsule()
                                    .fill(Palette.thumb)
                                    .shadow(color: Palette.shadow.opacity(0.14), radius: 8, y: 3)
                                    .matchedGeometryEffect(id: "thumb", in: namespace)
                            }
                        }
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(4)
        .glassControl(in: Capsule(), interactive: false)
        .sensoryFeedback(.selection, trigger: selection)
    }
}

/// A labelled input on glass, with a leaf ring while it has focus.
struct GlassField<Field: View>: View {
    let icon: String
    var focused = false
    @ViewBuilder let field: () -> Field

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(focused ? Palette.leaf : Palette.inkFaint)
                .frame(width: 22)
            field()
                .font(TypeScale.body)
                .foregroundStyle(Palette.ink)
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 54)
        .glassSurface(cornerRadius: 16, elevated: false)
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Palette.leaf.opacity(focused ? 0.8 : 0), lineWidth: 1.5)
        )
        .animation(.easeOut(duration: 0.18), value: focused)
    }
}

/// Empty and error states say what to do next.
struct GlassMessage: View {
    let symbol: String
    let title: String
    let message: String
    var tint: Color = Palette.leaf
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: symbol)
                .font(.system(size: 26, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 64, height: 64)
                .background(tint.opacity(0.14), in: Circle())
                .symbolEffect(.bounce, value: title)
            VStack(spacing: 6) {
                Text(title).font(TypeScale.headline).foregroundStyle(Palette.ink)
                Text(message).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                    .multilineTextAlignment(.center)
            }
            if let actionTitle, let action {
                Button(actionTitle, action: action).buttonStyle(GlassButtonStyle(tint: tint))
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 28).padding(.horizontal, 22)
        .glassSurface()
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.circle.fill").foregroundStyle(Palette.alert)
            Text(message).font(TypeScale.subhead).foregroundStyle(Palette.ink)
            Spacer(minLength: 0)
        }
        .padding(14)
        .glassSurface(cornerRadius: 16, tint: Palette.alert, elevated: false)
        .transition(.move(edge: .top).combined(with: .opacity))
    }
}

/// Glass rows for the native Form screens.
struct GlassRowBackground: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        if reduceTransparency {
            Palette.surfaceSolid
        } else {
            Rectangle().fill(.ultraThinMaterial).overlay(Color.white.opacity(0.22))
        }
    }
}

extension View {
    /// A native Form restyled for the glass screens.
    func glassForm(_ tone: DayPart? = nil) -> some View {
        self.scrollContentBackground(.hidden)
            .font(TypeScale.body)
            .foregroundStyle(Palette.ink)
            .tint(Palette.leaf)
            .ambientBackground(tone)
    }
}

// MARK: - Shared building blocks

/// A primary button's label that swaps to a spinner while its action runs,
/// keeping the button's size steady.
struct LoadingLabel: View {
    let title: String
    let busy: Bool

    var body: some View {
        ZStack {
            Text(title).opacity(busy ? 0 : 1)
            if busy { ProgressView().tint(.white) }
        }
    }
}

/// The icon-over-title tile used for quick actions, as a Button or a
/// NavigationLink label.
struct TileContent: View {
    let symbol: String
    let title: String

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: symbol)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(Palette.leaf)
                .frame(width: 42, height: 42)
                .background(Palette.leaf.opacity(0.13), in: Circle())
            Text(title).font(TypeScale.callout).foregroundStyle(Palette.ink)
                .lineLimit(1).minimumScaleFactor(0.85)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .glassSurface(cornerRadius: 20)
    }
}

/// A loading stand-in for a card: a leading bar or circle and a few text
/// lines, gently pulsing (still under Reduce Motion).
struct GlassPlaceholder: View {
    enum Leading { case bar, circle(CGFloat) }

    var leading: Leading = .circle(36)
    var lineWidths: [CGFloat] = [120, 180]
    var label = "Loading"
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 14) {
            switch leading {
            case .bar:
                Capsule().fill(Palette.inkFaint.opacity(0.3)).frame(width: 4, height: 60)
            case .circle(let size):
                Circle().fill(Palette.inkFaint.opacity(0.2)).frame(width: size, height: size)
            }
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(lineWidths.enumerated()), id: \.offset) { index, width in
                    RoundedRectangle(cornerRadius: 5)
                        .fill(Palette.inkFaint.opacity(0.24 - Double(index) * 0.05))
                        .frame(width: width, height: index == 0 ? 13 : 11)
                }
            }
            Spacer()
        }
        .padding(16)
        .glassSurface(elevated: false)
        .opacity(pulse ? 0.55 : 1)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 0.9).repeatForever()) { pulse = true }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
    }
}
