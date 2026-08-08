import SwiftUI

/// Minimal shared color tokens. Deliberately not a port of Tell-Us's
/// hand-built glass/ember aesthetic (Theme.swift) — Gummfit's visual design
/// is a later polish pass (Phase 7); this just keeps the placeholder screens
/// from hardcoding raw colors that would need a find-replace later.
enum GummfitTheme {
    static let accent = Color(red: 0x2E / 255, green: 0xC9 / 255, blue: 0x5C / 255)
    static let background = Color(red: 0x0B / 255, green: 0x12 / 255, blue: 0x14 / 255)
    static let textDim = Color.secondary
}
