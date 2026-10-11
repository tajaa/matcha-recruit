import SwiftUI

struct VersionHistoryView: View {
    @Environment(AppState.self) private var appState
    let versions: [MWDocumentVersion]
    let currentVersion: Int
    let onRevert: (Int) -> Void
    @State private var versionToRevert: Int?
    @State private var showConfirm = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Version History")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            Divider().opacity(0.3)

            if versions.isEmpty {
                Spacer()
                Text("No versions yet")
                    .foregroundColor(appState.themeTextSecondary)
                    .font(.system(size: 13))
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(versions.sorted(by: { $0.version > $1.version })) { version in
                            VersionRowView(
                                version: version,
                                isCurrent: version.version == currentVersion,
                                onRevert: {
                                    versionToRevert = version.version
                                    showConfirm = true
                                }
                            )
                        }
                    }
                    .padding(.vertical, 8)
                }
            }
        }
        .background(appState.themeCard)
        .confirmationDialog("Revert to v\(versionToRevert ?? 0)?", isPresented: $showConfirm) {
            Button("Revert") {
                if let v = versionToRevert { onRevert(v) }
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("The thread will be reverted to this version.")
        }
    }
}

struct VersionRowView: View {
    @Environment(AppState.self) private var appState
    let version: MWDocumentVersion
    let isCurrent: Bool
    let onRevert: () -> Void

    var formattedDate: String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: version.createdAt) {
            let display = DateFormatter()
            display.dateStyle = .short
            display.timeStyle = .short
            return display.string(from: date)
        }
        return version.createdAt
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text("v\(version.version)")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                    if isCurrent {
                        Text("current")
                            .font(.system(size: 10, weight: .medium))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(appState.themeAccent.opacity(0.18))
                            .foregroundColor(appState.themeAccent)
                            .cornerRadius(4)
                    }
                }

                if let summary = version.diffSummary, !summary.isEmpty {
                    Text(summary)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2)
                }

                Text(formattedDate)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary.opacity(0.7))
            }

            Spacer()

            if !isCurrent {
                Button("Revert") {
                    onRevert()
                }
                .buttonStyle(.plain)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(appState.assetWell)
                .cornerRadius(5)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(isCurrent ? appState.themeAccent.opacity(0.08) : Color.clear)
    }
}
