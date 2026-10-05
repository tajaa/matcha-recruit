import SwiftUI
import UIKit

// The app uses the system's own colors and surfaces; the emerald accent comes
// from the AccentColor asset. Type is Inter (SIL OFL, Resources/Fonts), with
// Inter Display for large titles, sized to the system text styles so Dynamic
// Type still applies.

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

    /// Inter Display ships in two weights; lighter requests use SemiBold.
    fileprivate var displayName: String { self == .bold ? "InterDisplay-Bold" : "InterDisplay-SemiBold" }
}

extension Font {
    /// Inter at a text style's default size, scaling with Dynamic Type. Sizes
    /// of 20 pt and up use the Display cut, which is drawn for large text.
    static func app(_ style: Font.TextStyle, _ weight: InterWeight? = nil) -> Font {
        let (size, standard) = style.interMetrics
        return inter(size, weight ?? standard, relativeTo: style)
    }

    static func inter(_ size: CGFloat, _ weight: InterWeight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom(size >= 20 ? weight.displayName : weight.textName, size: size, relativeTo: style)
    }
}

private extension Font.TextStyle {
    var interMetrics: (CGFloat, InterWeight) {
        switch self {
        case .largeTitle: (34, .bold)
        case .title: (28, .bold)
        case .title2: (22, .bold)
        case .title3: (20, .semibold)
        case .headline: (17, .semibold)
        case .callout: (16, .regular)
        case .subheadline: (15, .regular)
        case .footnote: (13, .regular)
        case .caption: (12, .regular)
        case .caption2: (11, .regular)
        default: (17, .regular)
        }
    }
}

extension Color {
    /// The emerald accent, read from the asset by name: `Color.brand`
    /// can resolve to system blue when the catalog accent is not applied.
    static let brand = Color("AccentColor")
}

// MARK: - UIKit chrome
//
// Navigation titles, tab labels and segmented controls are UIKit-drawn.

enum Appearance {
    static func configure() {
        func font(_ name: String, _ size: CGFloat, _ style: UIFont.TextStyle) -> UIFont {
            UIFontMetrics(forTextStyle: style).scaledFont(for: UIFont(name: name, size: size) ?? .systemFont(ofSize: size))
        }
        let nav = UINavigationBar.appearance()
        nav.largeTitleTextAttributes = [.font: font("InterDisplay-Bold", 34, .largeTitle)]
        nav.titleTextAttributes = [.font: font("Inter-SemiBold", 17, .headline)]
        let tab = font("Inter-Medium", 10, .caption2)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tab], for: .normal)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tab], for: .selected)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: font("Inter-Medium", 13, .footnote)], for: .normal)
    }
}

// MARK: - Day parts
//
// Crew vernacular: an opener, a mid, a closer. Each carries its own color so a
// week reads at a glance.

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
        case .opener: .orange
        case .mid: .brand
        case .closer: .indigo
        }
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
