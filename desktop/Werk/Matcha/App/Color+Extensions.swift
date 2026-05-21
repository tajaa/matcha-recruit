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
        case "light":     return grayBg
        case "cappuchin": return cappuchinDark
        default:          return zinc950
        }
    }

    /// Dynamic card/surface color, mirrors AppState.themeCard.
    static var cardBackground: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return grayCard
        case "cappuchin": return cappuchinCard
        default:          return zinc900
        }
    }

    /// Dynamic border color, mirrors AppState.themeBorder.
    static var borderColor: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return grayBorder
        case "cappuchin": return cappuchinBorder
        default:          return .white.opacity(0.1)
        }
    }

    // Grayscale light theme components (zinc scale, charcoal accent)
    static let grayBg = Color(red: 0.957, green: 0.957, blue: 0.961)            // zinc-100 #F4F4F5
    static let grayCard = Color.white                                           // #FFFFFF
    static let grayBorder = Color(red: 0.894, green: 0.894, blue: 0.906)        // zinc-200 #E4E4E7
    static let grayAccent = Color(red: 0.153, green: 0.153, blue: 0.165)        // zinc-800 #27272A
    static let grayAccentDark = Color(red: 0.094, green: 0.094, blue: 0.106)    // zinc-900 #18181B
    static let grayText = Color(red: 0.094, green: 0.094, blue: 0.106)          // zinc-900 #18181B
    static let grayTextSecondary = Color(red: 0.443, green: 0.443, blue: 0.478) // zinc-500 #71717A

    // Radial-gradient endpoints for the "muted elegance" depth backgrounds.
    // Center is a touch lighter than the flat theme bg, edges a touch darker —
    // a soft top-anchored spotlight that reads as depth without color.
    static let grayRadialCenter = Color(red: 0.992, green: 0.992, blue: 0.996)  // ~#FDFDFE
    static let grayRadialEdge   = Color(red: 0.914, green: 0.914, blue: 0.925)  // ~#E9E9EC
    static let darkRadialCenter = Color(red: 0.110, green: 0.110, blue: 0.122)  // ~#1C1C1F
    static let darkRadialEdge   = Color(red: 0.035, green: 0.035, blue: 0.047)  // ~#09090C
    static let cappuchinRadialCenter = Color(red: 0.176, green: 0.137, blue: 0.106) // ~#2D231B
    static let cappuchinRadialEdge   = Color(red: 0.102, green: 0.075, blue: 0.055) // ~#1A130E

    // Cappuchin theme components — warm espresso with clear tonal steps
    static let cappuchinDark = Color(red: 0.129, green: 0.098, blue: 0.075)     // Deep espresso bg #211913
    static let cappuchinCard = Color(red: 0.204, green: 0.157, blue: 0.122)     // Lifted mocha card #34281F
    static let cappuchinBorder = Color(red: 0.290, green: 0.231, blue: 0.180)   // Warm taupe line #4A3B2E
    static let cappuchinAccent = Color(red: 0.83, green: 0.64, blue: 0.45)      // Caramel accent #D4A373
    static let cappuchinAccentDark = Color(red: 0.70, green: 0.52, blue: 0.35)  // Latte brown #B0855A
    static let cappuchinText = Color(red: 0.95, green: 0.90, blue: 0.85)        // Milk cream #F5ECE3
    static let cappuchinSecondary = Color(red: 0.77, green: 0.71, blue: 0.65)   // Light latte text #C4B5A6
}
