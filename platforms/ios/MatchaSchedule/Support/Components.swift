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
    @Environment(\.colorScheme) private var scheme

    /// The accent is bright in dark mode, where white text on it is hard to read.
    private var ink: Color { scheme == .dark ? Color.black.opacity(0.85) : Color.white }

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
// Glass is for controls that float over content, never for the content itself.
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

    /// The one filled action on a screen, as tinted glass on iOS 26.
    @ViewBuilder
    func prominentGlassButton() -> some View {
        #if compiler(>=6.2)
        if #available(iOS 26.0, *) {
            self.buttonStyle(.glassProminent)
        } else {
            self.buttonStyle(.borderedProminent)
        }
        #else
        self.buttonStyle(.borderedProminent)
        #endif
    }
}

extension View {
    /// The one filled action on a form or sheet, in a row of its own.
    func primaryActionRow() -> some View {
        self.buttonStyle(.borderedProminent)
            .controlSize(.large)
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
    }
}
