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
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "platinum" {
        case "light":     return grayBg
        case "platinum":  return platinumBg
        case "cappuchin": return cappuchinDark
        case "graphite":  return graphiteBg
        default:          return zinc950
        }
    }

    /// Dynamic card/surface color, mirrors AppState.themeCard.
    static var cardBackground: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "platinum" {
        case "light":     return grayCard
        case "platinum":  return platinumCard
        case "cappuchin": return cappuchinCard
        case "graphite":  return graphiteCard
        default:          return zinc900
        }
    }

    /// Dynamic border color, mirrors AppState.themeBorder.
    static var borderColor: Color {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "platinum" {
        case "light":     return grayBorder
        case "platinum":  return platinumBorder
        case "cappuchin": return cappuchinBorder
        case "graphite":  return graphiteBorder
        default:          return .white.opacity(0.1)
        }
    }

    // ── MW semantic palette: grayscale scale + ONE burnt-amber accent ──────
    // Used by the TaskViewer / activity-graph surfaces so we ride a gray *scale*
    // (gray-300 … gray-900) for all structure/status and reserve burnt amber
    // (≈amber-700 on light, amber-500 on dark) as the single attention accent.
    // Theme-aware via `mw-theme` so views without AppState still adapt.
    private static var mwIsLightTheme: Bool {
        switch UserDefaults.standard.string(forKey: "mw-theme") ?? "platinum" {
        case "light", "platinum": return true
        default: return false
        }
    }
    /// Primary text — gray-900 on light, gray-200 on dark.
    static var mwInk: Color {
        mwIsLightTheme ? Color(red: 0.106, green: 0.114, blue: 0.133)
                       : Color(red: 0.898, green: 0.906, blue: 0.922)
    }
    /// Muted text / secondary — gray-500 on light, gray-400 on dark.
    static var mwInkSoft: Color {
        mwIsLightTheme ? Color(red: 0.416, green: 0.431, blue: 0.471)
                       : Color(red: 0.612, green: 0.639, blue: 0.686)
    }
    /// Strongest neutral accent (replaces the old green/blue "primary") —
    /// gray-800 on light, near-white on dark.
    static var mwInkStrong: Color {
        mwIsLightTheme ? Color(red: 0.169, green: 0.180, blue: 0.208)
                       : Color(red: 0.965, green: 0.969, blue: 0.976)
    }
    /// Hairline / faint rule — gray-300 on light, white@12% on dark.
    static var mwHairline: Color {
        mwIsLightTheme ? Color(red: 0.835, green: 0.847, blue: 0.875)
                       : Color.white.opacity(0.12)
    }
    /// Solid charcoal for filled action buttons that carry WHITE text — fixed
    /// (theme-independent) so it stays dark enough for white to read on every
    /// theme (light or dark).
    static let mwSolid = Color(red: 0.169, green: 0.180, blue: 0.208)   // #2B2E35
    /// The single accent — burnt amber. amber-700 on light, amber-500 on dark.
    static var mwAttention: Color {
        mwIsLightTheme ? Color(red: 0.706, green: 0.325, blue: 0.035)   // #B45309
                       : Color(red: 0.961, green: 0.620, blue: 0.043)   // #F59E0B
    }
    /// Distinct gray *levels* per collaborator (honors "emphasis on scale" —
    /// people are told apart by gray weight + their avatar photo, not by hue).
    static func mwLaneGray(_ index: Int) -> Color {
        let light: [Color] = [
            Color(red: 0.216, green: 0.255, blue: 0.318),   // gray-700
            Color(red: 0.420, green: 0.447, blue: 0.502),   // gray-500
            Color(red: 0.612, green: 0.639, blue: 0.686),   // gray-400
            Color(red: 0.294, green: 0.333, blue: 0.388),   // gray-600
        ]
        let dark: [Color] = [
            Color(red: 0.820, green: 0.835, blue: 0.859),   // gray-300
            Color(red: 0.612, green: 0.639, blue: 0.686),   // gray-400
            Color(red: 0.706, green: 0.722, blue: 0.749),   // gray-350
            Color(red: 0.420, green: 0.447, blue: 0.502),   // gray-500
        ]
        let p = mwIsLightTheme ? light : dark
        return p[abs(index) % p.count]
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

    // Platinum theme — the signature MW look (default). A cool light-gray base
    // with a soft light-gray radial gradient and a dark cool-charcoal accent
    // (the MW monogram color). Grayscale, faintly blue-cool, premium-light.
    static let platinumBg          = Color(red: 0.925, green: 0.929, blue: 0.941) // #ECEDF0 cool light gray
    static let platinumCard        = Color(red: 0.984, green: 0.988, blue: 0.996) // #FBFCFE near-white card
    static let platinumSidebar     = Color(red: 0.871, green: 0.878, blue: 0.902) // #DEE0E6 darker than body (rail contrast)
    static let platinumBorder      = Color(red: 0.835, green: 0.847, blue: 0.875) // #D5D8DF hairline
    static let platinumAccent      = Color(red: 0.169, green: 0.180, blue: 0.208) // #2B2E35 dark cool charcoal (MW mark)
    static let platinumAccentDark  = Color(red: 0.106, green: 0.114, blue: 0.133) // #1B1D22
    static let platinumText        = Color(red: 0.106, green: 0.114, blue: 0.133) // #1B1D22
    static let platinumSecondary   = Color(red: 0.416, green: 0.431, blue: 0.471) // #6A6E78 cool gray text
    static let platinumRadialCenter = Color(red: 0.969, green: 0.973, blue: 0.984) // #F7F8FB bright spotlight
    static let platinumRadialEdge   = Color(red: 0.863, green: 0.871, blue: 0.898) // #DCDEE5 darker edge
}
