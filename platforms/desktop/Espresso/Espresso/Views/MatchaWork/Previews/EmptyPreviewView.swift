import SwiftUI

struct EmptyPreviewView: View {
    @Environment(AppState.self) private var appState
    var message = "No preview available"
    var icon = "doc"

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 22, weight: .light))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 52, height: 52)
                .background(Circle().fill(appState.assetWell))
            Text(message)
                .font(.espresso(size: 12.5))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 220, maxHeight: .infinity)
    }
}
