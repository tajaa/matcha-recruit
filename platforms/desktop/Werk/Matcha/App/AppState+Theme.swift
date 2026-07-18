import SwiftUI

/// Theme-derived colors. The `appTheme` storage + didSet stay on the main
/// AppState; these are pure computed accessors read all over the UI.
extension AppState {
    var themeBg: Color {
        switch appTheme {
        case "light": return Color.grayBg
        case "platinum": return Color.platinumBg
        case "cappuchin": return Color.cappuchinDark
        case "graphite": return Color.graphiteBg
        default: return Color.zinc950
        }
    }

    var themeCard: Color {
        switch appTheme {
        case "light": return Color.grayCard
        case "platinum": return Color.platinumCard
        case "cappuchin": return Color.cappuchinCard
        case "graphite": return Color.graphiteCard
        default: return Color.zinc900
        }
    }

    /// Sidebar background — deliberately CONTRASTS the body (`themeBg`): lighter
    /// than the near-black dark bg, lighter than the espresso cappuchin bg, and
    /// DARKER than the light-mode body, so the nav rail always separates from the
    /// main content.
    var themeSidebar: Color {
        switch appTheme {
        case "light": return Color.graySidebar
        case "platinum": return Color.platinumSidebar
        case "cappuchin": return Color.cappuchinCard
        case "graphite": return Color.graphiteSidebar
        default: return Color.zinc900
        }
    }

    var themeBorder: Color {
        switch appTheme {
        case "light": return Color.grayBorder
        case "platinum": return Color.platinumBorder
        case "cappuchin": return Color.cappuchinBorder
        case "graphite": return Color.graphiteBorder
        default: return Color.white.opacity(0.1)
        }
    }

    var themeAccent: Color {
        switch appTheme {
        case "light": return Color.grayAccent
        case "platinum": return Color.platinumAccent
        case "cappuchin": return Color.cappuchinAccent
        case "graphite": return Color.graphiteAccent
        default: return Color.matcha500
        }
    }

    var themeAccentDark: Color {
        switch appTheme {
        case "light": return Color.grayAccentDark
        case "platinum": return Color.platinumAccentDark
        case "cappuchin": return Color.cappuchinAccentDark
        case "graphite": return Color.graphiteAccentDark
        default: return Color.matcha600
        }
    }

    var themeText: Color {
        switch appTheme {
        case "light": return Color.grayText
        case "platinum": return Color.platinumText
        case "cappuchin": return Color.cappuchinText
        case "graphite": return Color.graphiteText
        default: return Color.white
        }
    }

    /// Foreground for content sitting ON the accent color (e.g. button labels).
    /// Caramel cappuchin accent is light, so it needs dark text; charcoal and
    /// matcha green accents need white.
    var themeOnAccent: Color {
        switch appTheme {
        case "cappuchin": return Color.cappuchinDark
        case "graphite": return Color.graphiteOnAccent
        default: return Color.white
        }
    }

    var themeTextSecondary: Color {
        switch appTheme {
        case "light": return Color.grayTextSecondary
        case "platinum": return Color.platinumSecondary
        case "cappuchin": return Color.cappuchinSecondary
        case "graphite": return Color.graphiteSecondary
        default: return Color.secondary
        }
    }

    var lightMode: Bool {
        return isLightFamily
    }

    /// Light-family themes (`light` + `platinum`) share the light-mode render
    /// path: light card shadows instead of dark borders, `.light` colorScheme,
    /// light chat bubbles. New light themes MUST join this, or chrome that keys
    /// off `appTheme == "light"` renders in the dark path on top of a light bg.
    var isLightFamily: Bool {
        return appTheme == "light" || appTheme == "platinum"
    }

    /// Graphite — the minimalist grayscale theme. Gates the stripped-down ASCII
    /// chrome (rule headers, `[ ]` checkboxes, flat hero) so the other three
    /// themes keep their normal SF-Symbol styling untouched.
    var isGraphite: Bool {
        return appTheme == "graphite"
    }
}
