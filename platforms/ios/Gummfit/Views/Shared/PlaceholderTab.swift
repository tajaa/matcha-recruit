import SwiftUI

/// Stand-in for tabs whose real content lands in a later phase (plan §9
/// phasing table) — keeps the tab bar shape stable across phases instead of
/// growing tabs mid-stream.
struct PlaceholderTab: View {
    let title: String

    var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                Text("Coming soon")
                    .foregroundStyle(GummfitTheme.textDim)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(GummfitTheme.background).ignoresSafeArea())
            .navigationTitle(title)
        }
    }
}
