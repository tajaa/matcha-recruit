import SwiftUI

/// The compact thread's "Chat | <document>" switch: one pill slides between
/// the two. `unseen` dots the document side when it changed out of sight.
struct AssetTabSwitch: View {
    @Environment(AppState.self) private var appState
    @Binding var showingAsset: Bool
    let kind: AssetKind
    var unseen = false
    @Namespace private var pill

    var body: some View {
        HStack(spacing: 2) {
            segment(asset: false, title: "Chat", icon: "bubble.left.and.bubble.right")
            segment(asset: true, title: kind.name, icon: kind.icon, dot: unseen)
        }
        .padding(3)
        .background(Capsule().fill(appState.themeText.opacity(0.06)))
        .overlay(Capsule().stroke(appState.themeBorder, lineWidth: 0.5))
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(appState.themeBg)
        .overlay(Rectangle().fill(appState.themeBorder).frame(height: 0.5), alignment: .bottom)
    }

    private func segment(asset: Bool, title: String, icon: String, dot: Bool = false) -> some View {
        let selected = showingAsset == asset
        return Button {
            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) { showingAsset = asset }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 10.5, weight: .medium))
                Text(title).font(.espresso(size: 11.5, weight: selected ? .semibold : .regular))
                if dot {
                    Circle().fill(kind.tint).frame(width: 6, height: 6)
                }
            }
            .foregroundColor(selected ? appState.themeText : appState.themeTextSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background {
                if selected {
                    Capsule()
                        .fill(appState.themeCard)
                        .shadow(color: .black.opacity(appState.isLightFamily ? 0.1 : 0.35), radius: 3, y: 1)
                        .matchedGeometryEffect(id: "pill", in: pill)
                }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}
