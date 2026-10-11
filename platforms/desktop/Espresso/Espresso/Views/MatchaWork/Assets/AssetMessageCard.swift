import SwiftUI

/// Marks a reply that created or changed the thread's document: what it is,
/// which version, what changed, and a way to open it.
struct AssetMessageCard: View {
    @Environment(AppState.self) private var appState
    let version: Int
    let asset: ThreadAssetContext
    @State private var hovering = false

    private var summary: String? {
        let text = asset.versions.first { $0.version == version }?.diffSummary?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (text?.isEmpty ?? true) ? nil : text
    }

    var body: some View {
        let tint = asset.kind.tint
        let isLatest = version == asset.currentVersion
        Button(action: asset.open) {
            HStack(alignment: .top, spacing: 11) {
                AssetIconTile(kind: asset.kind, size: 30)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text("\(asset.kind.name) · v\(version)")
                            .font(.espresso(size: 12, weight: .semibold))
                            .foregroundColor(appState.themeText)
                        if isLatest {
                            Text("Latest")
                                .font(.espresso(size: 9.5, weight: .semibold))
                                .foregroundColor(tint)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 1.5)
                                .background(Capsule().fill(tint.opacity(0.13)))
                        }
                    }
                    if let title = asset.title {
                        Text(title)
                            .font(.espresso(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                            .lineLimit(1)
                    }
                    Text(summary ?? (version <= 1 ? "Created" : "Updated"))
                        .font(.espresso(size: 11.5))
                        .foregroundColor(appState.themeText.opacity(0.78))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 1)
                }
                Spacer(minLength: 8)
                HStack(spacing: 3) {
                    Text("Open")
                    Image(systemName: "arrow.up.right")
                        .font(.system(size: 9, weight: .bold))
                }
                .font(.espresso(size: 11, weight: .semibold))
                .foregroundColor(hovering ? tint : appState.themeTextSecondary)
                .padding(.top, 2)
            }
            .padding(11)
            .frame(maxWidth: 420, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(appState.themeCard)
            )
            .overlay(alignment: .leading) {
                // The asset's color as a thin rail, like a calendar entry.
                UnevenRoundedRectangle(topLeadingRadius: 10, bottomLeadingRadius: 10, style: .continuous)
                    .fill(tint)
                    .frame(width: 3)
            }
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(hovering ? tint.opacity(0.6) : appState.themeBorder, lineWidth: hovering ? 1 : 0.5)
            )
            .shadow(color: .black.opacity(appState.isLightFamily ? 0.05 : 0.2), radius: hovering ? 10 : 5, y: 2)
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(.easeOut(duration: 0.12), value: hovering)
        .help("Open the \(asset.kind.name.lowercased())")
    }
}
