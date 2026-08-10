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

    /// The navigation rail always uses the opposite color mode of the body:
    /// dark for light-family themes and light for dark-family themes.
    var isSidebarDark: Bool { isLightFamily }

    var themeSidebar: Color {
        isSidebarDark
            ? Color(red: 0.075, green: 0.078, blue: 0.086)
            : Color(red: 0.775, green: 0.770, blue: 0.750)
    }

    var themeSidebarCard: Color {
        isSidebarDark ? Color.white.opacity(0.08) : Color.black.opacity(0.055)
    }

    var themeSidebarBorder: Color {
        isSidebarDark ? Color.white.opacity(0.12) : Color.black.opacity(0.10)
    }

    var themeSidebarText: Color {
        isSidebarDark ? Color.white.opacity(0.96) : Color(red: 0.095, green: 0.098, blue: 0.108)
    }

    var themeSidebarTextSecondary: Color {
        isSidebarDark ? Color.white.opacity(0.68) : Color(red: 0.245, green: 0.245, blue: 0.255)
    }

    var themeSidebarAccent: Color {
        isSidebarDark ? Color.matcha500 : Color.matcha600
    }

    var themeSidebarOnAccent: Color {
        isSidebarDark ? Color.zinc900 : Color.white
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
        case "light", "platinum": return Color.matcha600
        case "cappuchin", "graphite": return Color.matcha500
        default: return Color.matcha500
        }
    }

    var themeAccentDark: Color {
        switch appTheme {
        case "light", "platinum", "cappuchin", "graphite": return Color.matcha600
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
    /// Amber sits on dark surfaces; filled actions use white labels.
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
