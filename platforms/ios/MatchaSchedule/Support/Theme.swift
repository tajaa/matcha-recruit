import SwiftUI
import UIKit

// MARK: - Palette
//
// Matcha, not coffee-shop cream: a cool pale "foam" base, a leaf accent, and
// three day-part lights that every shift carries (see `DayPart`).

enum Palette {
    /// Deep ceremonial green-black: primary text in light mode.
    static let ink = Color(light: 0x16261D, dark: 0xEAF2E6)
    /// Secondary text.
    static let inkSoft = Color(light: 0x4F6356, dark: 0xA9BAAE)
    /// Tertiary text, hairlines.
    static let inkFaint = Color(light: 0x8A9A8F, dark: 0x6F8076)
    /// Base background.
    static let foam = Color(light: 0xF1F6EC, dark: 0x0A120D)
    /// Primary accent: buttons, selection, links.
    static let leaf = Color(light: 0x4E8F41, dark: 0x8CCB74)
    /// Brighter leaf for gradients and glows.
    static let sprout = Color(light: 0x9FD37F, dark: 0xB5E59A)
    /// Opener light.
    static let dawn = Color(light: 0xF39A6B, dark: 0xFFB08A)
    /// Closer light.
    static let dusk = Color(light: 0x7C6CE6, dark: 0xA79BFF)
    static let alert = Color(light: 0xC2413A, dark: 0xFF7B72)
    static let amber = Color(light: 0xC98A12, dark: 0xF2C14E)
    /// The raised "you are here" fill: segmented thumb, focused day.
    static let thumb = Color(light: 0xFFFFFF, dark: 0x33453A)
    /// Opaque card fill for Reduce Transparency.
    static let surfaceSolid = Color(light: 0xFFFFFF, dark: 0x16211A)
    static let shadow = Color(light: 0x1C3324, dark: 0x000000)

    /// The leaf gradient behind primary actions and the employee's own bubbles.
    static let leafGradient = LinearGradient(
        colors: [Color(light: 0x5FA84E, dark: 0x7FC266), Color(light: 0x3D7A34, dark: 0x4E8F41)],
        startPoint: .topLeading, endPoint: .bottomTrailing
    )
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: alpha)
    }

    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 0xFF) / 255,
                           green: CGFloat((hex >> 8) & 0xFF) / 255,
                           blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
        })
    }
}

// MARK: - Type
//
// Inter throughout; Inter Display (its optical size for large text) carries
// titles and the big clock numerals. Every size scales with Dynamic Type.

enum InterWeight {
    case regular, medium, semibold, bold

    fileprivate var textName: String {
        switch self {
        case .regular: "Inter-Regular"
        case .medium: "Inter-Medium"
        case .semibold: "Inter-SemiBold"
        case .bold: "Inter-Bold"
        }
    }

    fileprivate var displayName: String {
        self == .bold ? "InterDisplay-Bold" : "InterDisplay-SemiBold"
    }
}

extension Font {
    static func inter(_ size: CGFloat, _ weight: InterWeight = .regular,
                      relativeTo style: Font.TextStyle = .body) -> Font {
        .custom(weight.textName, size: size, relativeTo: style)
    }

    static func interDisplay(_ size: CGFloat, _ weight: InterWeight = .bold,
                             relativeTo style: Font.TextStyle = .largeTitle) -> Font {
        .custom(weight.displayName, size: size, relativeTo: style)
    }
}

/// The type scale. Views use these, never raw sizes.
enum TypeScale {
    static let hero = Font.interDisplay(40, .bold, relativeTo: .largeTitle)
    static let clock = Font.interDisplay(30, .bold, relativeTo: .title)
    static let title = Font.interDisplay(22, .semibold, relativeTo: .title2)
    static let headline = Font.inter(17, .semibold, relativeTo: .headline)
    static let body = Font.inter(16, .regular, relativeTo: .body)
    static let callout = Font.inter(15, .medium, relativeTo: .callout)
    static let subhead = Font.inter(14, .regular, relativeTo: .subheadline)
    static let caption = Font.inter(12, .medium, relativeTo: .caption)
    static let eyebrow = Font.inter(11, .semibold, relativeTo: .caption2)
}

// MARK: - Spacing and shape (4-pt grid)

enum Metrics {
    static let gutter: CGFloat = 20
    static let stack: CGFloat = 12
    static let heroRadius: CGFloat = 30
    static let cardRadius: CGFloat = 22
    static let innerRadius: CGFloat = 14
}

// MARK: - Day parts
//
// Crew vernacular: an opener, a mid, a closer. Each carries its own light so a
// week reads at a glance, and the ambient background leans toward the light of
// the employee's next shift.

enum DayPart: String {
    case opener, mid, closer

    /// Shift times are the store's clock face tagged UTC, so the hour is read
    /// in UTC, never converted.
    init(wallClockISO iso: String) {
        let hour = WallClock.date(iso).map { WallClock.hour(of: $0) } ?? 12
        switch hour {
        case ..<10: self = .opener
        case ..<15: self = .mid
        default: self = .closer
        }
    }

    var label: String {
        switch self {
        case .opener: "Opener"
        case .mid: "Mid"
        case .closer: "Closer"
        }
    }

    var symbol: String {
        switch self {
        case .opener: "sunrise.fill"
        case .mid: "sun.max.fill"
        case .closer: "moon.stars.fill"
        }
    }

    var color: Color {
        switch self {
        case .opener: Palette.dawn
        case .mid: Palette.leaf
        case .closer: Palette.dusk
        }
    }

    var gradient: LinearGradient {
        LinearGradient(colors: [color, color.opacity(0.55)], startPoint: .top, endPoint: .bottom)
    }
}

// MARK: - Appearance preference
//
// Light, Dark, or follow the system. Applied as the window's interface style
// rather than `preferredColorScheme`, so sheets follow it and switching back
// to System takes effect immediately.

enum AppearancePreference: String, CaseIterable, Identifiable {
    case system, light, dark

    static let storageKey = "schedule.appearance"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .system: "System"
        case .light: "Light"
        case .dark: "Dark"
        }
    }

    var interfaceStyle: UIUserInterfaceStyle {
        switch self {
        case .system: .unspecified
        case .light: .light
        case .dark: .dark
        }
    }

    @MainActor
    static func apply(_ preference: AppearancePreference, animated: Bool = false) {
        for scene in UIApplication.shared.connectedScenes {
            guard let windowScene = scene as? UIWindowScene else { continue }
            for window in windowScene.windows where window.overrideUserInterfaceStyle != preference.interfaceStyle {
                if animated {
                    UIView.transition(with: window, duration: 0.3, options: .transitionCrossDissolve) {
                        window.overrideUserInterfaceStyle = preference.interfaceStyle
                    }
                } else {
                    window.overrideUserInterfaceStyle = preference.interfaceStyle
                }
            }
        }
    }
}

// MARK: - UIKit chrome
//
// Navigation titles and tab labels are UIKit-drawn; give them Inter too.

enum Appearance {
    static func configure() {
        let large = UIFont(name: "InterDisplay-Bold", size: 34) ?? .systemFont(ofSize: 34, weight: .bold)
        let inline = UIFont(name: "Inter-SemiBold", size: 17) ?? .systemFont(ofSize: 17, weight: .semibold)
        let ink = UIColor(Palette.ink)
        let nav = UINavigationBar.appearance()
        nav.largeTitleTextAttributes = [
            .font: UIFontMetrics(forTextStyle: .largeTitle).scaledFont(for: large),
            .foregroundColor: ink,
        ]
        nav.titleTextAttributes = [
            .font: UIFontMetrics(forTextStyle: .headline).scaledFont(for: inline),
            .foregroundColor: ink,
        ]
        let tab = UIFont(name: "Inter-Medium", size: 10) ?? .systemFont(ofSize: 10, weight: .medium)
        UITabBar.appearance().unselectedItemTintColor = UIColor(Palette.inkSoft)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tab], for: .normal)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tab], for: .selected)
        let bar = UIFont(name: "Inter-Medium", size: 17) ?? .systemFont(ofSize: 17, weight: .medium)
        UIBarButtonItem.appearance().setTitleTextAttributes([.font: bar], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes(
            [.font: UIFont(name: "Inter-Medium", size: 13) ?? .systemFont(ofSize: 13)], for: .normal
        )
    }
}
