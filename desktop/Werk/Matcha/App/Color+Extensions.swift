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
        case "graphite":  return graphiteBg
        default:          return zinc950
        }
    }

    /// Dynamic card/surface color, mirrors AppState.themeCard.
    static var cardBackground: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return grayCard
        case "cappuchin": return cappuchinCard
        case "graphite":  return graphiteCard
        default:          return zinc900
        }
    }

    /// Dynamic border color, mirrors AppState.themeBorder.
    static var borderColor: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "dark" {
        case "light":     return grayBorder
        case "cappuchin": return cappuchinBorder
        case "graphite":  return graphiteBorder
        default:          return .white.opacity(0.1)
        }
    }

    // Grayscale light theme components (zinc scale, charcoal accent)
    static let grayBg = Color(red: 0.957, green: 0.957, blue: 0.961)            // zinc-100 #F4F4F5
    static let grayCard = Color.white                                           // #FFFFFF
    static let grayBorder = Color(red: 0.894, green: 0.894, blue: 0.906)        // zinc-200 #E4E4E7
    static let graySidebar = Color(red: 0.871, green: 0.871, blue: 0.886)       // ~zinc-250 #DEDEE2 — darker than body for sidebar contrast
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

    // Graphite theme — minimalist neutral grayscale. A dark-gray base with a
    // medium-gray radial gradient (the "actual gradient" the flat dark theme
    // lacks), a monochrome (hue-free) accent, soft off-white text, and low
    // hairline borders. Stripped down + elegant; nothing tinted.
    static let graphiteBg          = Color(red: 0.110, green: 0.110, blue: 0.118) // #1C1C1E neutral dark gray
    static let graphiteCard        = Color(red: 0.149, green: 0.149, blue: 0.161) // #262629 lifted surface
    static let graphiteSidebar     = Color(red: 0.176, green: 0.176, blue: 0.188) // #2D2D30 lighter than body (rail contrast)
    static let graphiteBorder      = Color(red: 0.235, green: 0.235, blue: 0.251) // #3C3C40 hairline
    static let graphiteAccent      = Color(red: 0.612, green: 0.612, blue: 0.639) // #9C9CA3 medium-light gray accent
    static let graphiteAccentDark  = Color(red: 0.467, green: 0.467, blue: 0.490) // #77777D
    static let graphiteText        = Color(red: 0.894, green: 0.894, blue: 0.910) // #E4E4E8 soft white
    static let graphiteSecondary   = Color(red: 0.557, green: 0.557, blue: 0.584) // #8E8E95 medium gray
    static let graphiteOnAccent    = Color(red: 0.110, green: 0.110, blue: 0.118) // dark text on the light-gray accent
    static let graphiteRadialCenter = Color(red: 0.176, green: 0.176, blue: 0.188) // #2D2D30 medium-gray spotlight
    static let graphiteRadialEdge   = Color(red: 0.086, green: 0.086, blue: 0.094) // #161618 darker edge
}
