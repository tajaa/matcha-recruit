import SwiftUI
import UIKit

// The app uses the system's own type, colors and surfaces; the emerald accent
// comes from the AccentColor asset. The only app-specific color is the day
// part below.

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
        case .mid: .accentColor
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
