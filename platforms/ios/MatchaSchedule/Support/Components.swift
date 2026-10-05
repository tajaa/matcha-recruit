import SwiftUI

// The few pieces the system does not provide. Everything else is a stock
// List, Form, Picker or button style.

struct StatusPill: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.app(.caption, .medium))
            .foregroundStyle(color)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.15), in: Capsule())
    }
}

struct Avatar: View {
    let name: String
    var size: CGFloat = 40

    private var initials: String {
        let parts = name.split(separator: " ").prefix(2)
        let letters = parts.compactMap(\.first).map(String.init).joined()
        return letters.isEmpty ? "·" : letters.uppercased()
    }

    /// A stable color per person, so a coworker keeps theirs.
    private var tone: DayPart {
        let sum = name.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        return [DayPart.opener, .mid, .closer][sum % 3]
    }

    var body: some View {
        Text(initials)
            .font(.inter(size * 0.38, .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(tone.color, in: Circle())
            .accessibilityHidden(true)
    }
}

/// A full-width button label that swaps to a spinner while its action runs,
/// keeping the button's size steady.
struct LoadingLabel: View {
    let title: String
    let busy: Bool
    /// Filled buttons are the text colour, so their label is the page colour.
    private var ink: Color { Color(.systemBackground) }

    var body: some View {
        ZStack {
            Text(title).opacity(busy ? 0 : 1)
            if busy { ProgressView().tint(ink) }
        }
        .foregroundStyle(ink)
        .frame(maxWidth: .infinity)
    }
}

/// A failure, in a list row: what went wrong and, where it helps, a retry.
struct ErrorRow: View {
    let message: String
    var retry: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(message, systemImage: "exclamationmark.circle")
                .font(.app(.subheadline))
                .foregroundStyle(.red)
            if let retry {
                Button("Try again", action: retry)
                    .font(.app(.subheadline))
                    .buttonStyle(.borderless)
            }
        }
    }
}

struct TightLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 5) {
            configuration.icon.imageScale(.small)
            configuration.title
        }
    }
}

// MARK: - Liquid Glass
//
// Glass is the floating layer: bars, controls and the one hero piece on a
// screen. Content sits beneath it on quiet cards (`cardRow`), never on glass.
// Two things glass cannot do: sit on other glass, or be rotated (it mis-sizes).
//
// `glassEffect` and the glass button styles only exist in the iOS 26 SDK.
// `#available` is a runtime check and does not stop an older SDK failing to
// compile the call, so the compiler check keeps Xcode 16 builds (CI's macos-15
// image) working; they, and iOS 17/18 devices, take the fallback.

extension View {
    /// A floating panel: Liquid Glass on iOS 26, a material before it.
    @ViewBuilder
    func glassPanel(in shape: some Shape) -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.glassEffect(.regular, in: shape)
        } else {
            self.background(.regularMaterial, in: shape)
        }
        #else
        self.background(.regularMaterial, in: shape)
        #endif
    }

    /// The one filled action on a screen: glass in the text colour (white on
    /// dark, black on light), so it stands out without adding a colour.
    @ViewBuilder
    func prominentGlassButton() -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.buttonStyle(.glassProminent).tint(Color.primary)
        } else {
            self.buttonStyle(.borderedProminent).tint(Color.primary)
        }
        #else
        self.buttonStyle(.borderedProminent).tint(Color.primary)
        #endif
    }

    /// Secondary actions, as clear glass on iOS 26.
    @ViewBuilder
    func glassButton() -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.buttonStyle(.glass)
        } else {
            self.buttonStyle(.bordered)
        }
        #else
        self.buttonStyle(.bordered)
        #endif
    }

    /// The tab bar steps back while content scrolls, on iOS 26.
    @ViewBuilder
    func tabBarMinimizesOnScroll() -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.tabBarMinimizeBehavior(.onScrollDown)
        } else {
            self
        }
        #else
        self
        #endif
    }
}

/// The hero piece of a screen: the next shift, an offer, the profile.
struct GlassHero<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassPanel(in: RoundedRectangle(cornerRadius: 26, style: .continuous))
    }
}

// MARK: - Backdrop and cards

/// The light behind every screen. Sign-in gets colour, slowly drifting (still
/// under Reduce Motion); everywhere else it is neutral and still, so the glass
/// and the content carry the screen.
struct AppBackdrop: View {
    var vivid = false
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var colors: [Color] {
        let hex: [UInt32]
        switch (vivid, scheme == .dark) {
        case (true, true):
            hex = [0x3B2A12, 0x06231B, 0x1B2A63,
                   0x062019, 0x0F6B4C, 0x06231B,
                   0x020B08, 0x083226, 0x03130E]
        case (true, false):
            hex = [0xFFDDB8, 0xDDF6EA, 0xB4EBD4,
                   0xF6FCF8, 0xC4F0DD, 0x98E2C4,
                   0xFFFFFF, 0xE6F8F0, 0xC6F0DE]
        // Neutral on purpose: graphite and paper. Colour is left to the few
        // things that mean something (today, unread, a shift's day part).
        case (false, true):
            hex = [0x24272B, 0x15171A, 0x1B1E22,
                   0x0B0C0E, 0x101113, 0x0B0C0E,
                   0x000000, 0x000000, 0x000000]
        case (false, false):
            hex = [0xFFFFFF, 0xF3F4F6, 0xE9EBEF,
                   0xF5F6F8, 0xF1F2F5, 0xECEEF1,
                   0xF1F2F5, 0xF1F2F5, 0xF1F2F5]
        }
        return hex.map { value in
            Color(.sRGB, red: Double((value >> 16) & 0xFF) / 255, green: Double((value >> 8) & 0xFF) / 255,
                  blue: Double(value & 0xFF) / 255)
        }
    }

    var body: some View {
        Group {
            if #available(iOS 18.0, *) {
                if vivid {
                    TimelineView(.animation(minimumInterval: 1.0 / 20, paused: reduceMotion)) { context in
                        MeshGradient(width: 3, height: 3,
                                     points: points(at: reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate),
                                     colors: colors)
                    }
                } else {
                    MeshGradient(width: 3, height: 3, points: points(at: 0), colors: colors)
                }
            } else {
                LinearGradient(colors: [colors[0], colors[4], colors[8]], startPoint: .topLeading, endPoint: .bottomTrailing)
            }
        }
        .ignoresSafeArea()
    }

    private func points(at time: TimeInterval) -> [SIMD2<Float>] {
        let t = Float(time)
        func drift(_ speed: Float, _ phase: Float, _ amount: Float) -> Float { sin(t * speed + phase) * amount }
        // The calm backdrop keeps its colour in the top third.
        let middle: Float = vivid ? 0.45 : 0.3
        return [
            [0, 0], [0.5 + drift(0.21, 0, 0.10), 0], [1, 0],
            [0, middle + drift(0.17, 1, 0.08)],
            [0.5 + drift(0.13, 2, 0.14), middle + drift(0.15, 3, 0.10)],
            [1, middle + drift(0.19, 4, 0.08)],
            [0, 1], [0.5 + drift(0.23, 5, 0.10), 1], [1, 1],
        ]
    }
}

/// The quiet title above a group of cards.
struct SectionLabel: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.app(.subheadline, .semibold))
            .foregroundStyle(Color.secondary)
            .padding(.leading, 4)
            .bareRow(top: 14, bottom: 0)
    }
}

/// The fill of a content card: a thin pane with a lit top edge, the gloss of
/// glass without stacking real glass down a whole list.
struct CardFill: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        let dark = scheme == .dark
        shape
            .fill(reduceTransparency
                  ? AnyShapeStyle(Color(.secondarySystemGroupedBackground))
                  : AnyShapeStyle(LinearGradient(
                        colors: dark ? [Color.white.opacity(0.10), Color.white.opacity(0.04)]
                                     : [Color.white.opacity(0.95), Color.white.opacity(0.70)],
                        startPoint: .top, endPoint: .bottom)))
            .overlay {
                shape.strokeBorder(LinearGradient(
                    colors: dark ? [Color.white.opacity(0.22), Color.white.opacity(0.03)]
                                 : [Color.white, Color.black.opacity(0.06)],
                    startPoint: .top, endPoint: .bottom), lineWidth: 1)
            }
            .shadow(color: Color.black.opacity(dark ? 0 : 0.05), radius: 8, y: 3)
    }
}

extension View {
    /// The calm backdrop behind a list, form or scroll view.
    func appBackdrop() -> some View {
        self.scrollContentBackground(.hidden)
            .background { AppBackdrop() }
    }

    /// A row of a plain List as a card of its own.
    func cardRow() -> some View {
        self.padding(.vertical, 8)
            .listRowInsets(EdgeInsets(top: 4, leading: 32, bottom: 4, trailing: 32))
            .listRowBackground(CardFill().padding(.horizontal, 16).padding(.vertical, 4))
            .listRowSeparator(.hidden)
    }

    /// A row of a plain List with nothing behind it: titles, heroes, buttons.
    func bareRow(top: CGFloat = 4, bottom: CGFloat = 4) -> some View {
        self.listRowInsets(EdgeInsets(top: top, leading: 16, bottom: bottom, trailing: 16))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
    }

    /// The one filled action on a form or sheet, in a row of its own.
    func primaryActionRow() -> some View {
        self.prominentGlassButton()
            .controlSize(.large)
            .buttonBorderShape(.capsule)
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
    }
}
