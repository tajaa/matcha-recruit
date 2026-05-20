import SwiftUI

extension Color {
    static let matcha500 = Color("matcha500")
    static let matcha600 = Color("matcha600")
    static let zinc800 = Color("zinc800")
    static let zinc900 = Color("zinc900")
    static let zinc950 = Color("zinc950")

    /// Dynamic — switches with the active theme so all views get the right
    /// background without individually reading AppState.
    static var appBackground: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return Color(white: 0.96)
        case "cappuchin": return cappuchinDark
        default:          return zinc950
        }
    }

    /// Dynamic card/surface color, mirrors AppState.themeCard.
    static var cardBackground: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return .white
        case "cappuchin": return cappuchinCard
        default:          return zinc900
        }
    }

    /// Dynamic border color, mirrors AppState.themeBorder.
    static var borderColor: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return .black.opacity(0.08)
        case "cappuchin": return cappuchinAccent.opacity(0.15)
        default:          return .white.opacity(0.1)
        }
    }

    // Cappuchin theme components
    static let cappuchinDark = Color(red: 0.15, green: 0.12, blue: 0.10)      // Espresso background #261E1A
    static let cappuchinCard = Color(red: 0.22, green: 0.18, blue: 0.15)      // Warm light espresso #382D26
    static let cappuchinAccent = Color(red: 0.83, green: 0.64, blue: 0.45)    // Caramel accent #D4A373
    static let cappuchinAccentDark = Color(red: 0.70, green: 0.52, blue: 0.35) // Latte brown #B0855A
    static let cappuchinText = Color(red: 0.95, green: 0.90, blue: 0.85)      // Milk cream #F5ECE3
    static let cappuchinSecondary = Color(red: 0.75, green: 0.70, blue: 0.65) // Light latte text #C0B4A9
}
