import SwiftUI

/// Sidebar list of journals visible to the current user. Selection writes
/// `appState.selectedJournalId` and clears other selection slots so
/// ContentView routes to JournalDetailView. Refreshes on
/// `journalsListGeneration` bumps from sibling views (NewJournalSheet).
struct JournalListView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true

    @State private var journals: [MWJournal] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            if showHeader {
                HStack {
                    Text("Journals")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                Divider().opacity(0.3)
            }

            if isLoading {
                ProgressView().tint(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 12)
            } else if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.8))
                    .padding(8)
            } else if journals.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "book.closed").font(.system(size: 22)).foregroundColor(.secondary)
                    Text("No journals yet").font(.system(size: 11)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 16)
            } else {
                LazyVStack(spacing: 0) {
                    ForEach(journals) { j in
                        row(j)
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .task { await load() }
        .onChange(of: appState.journalsListGeneration) { _, _ in
            Task { await load() }
        }
    }

    private func row(_ j: MWJournal) -> some View {
        let selected = appState.selectedJournalId == j.id
        return Button {
            appState.selectedJournalId = j.id
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.selectedChannelId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            HStack(spacing: 8) {
                Image(systemName: j.icon ?? "book")
                    .font(.system(size: 11))
                    .foregroundColor(colorFor(j.color))
                    .frame(width: 16)
                VStack(alignment: .leading, spacing: 1) {
                    Text(j.title)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1)
                    if let n = j.entryCount, n > 0 {
                        Text("\(n) entr\(n == 1 ? "y" : "ies")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .sidebarRowStyle(isSelected: selected)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// Map the stored color name to a SwiftUI Color. Free-form column on
    /// the backend; constrain client-side so the picker stays sane.
    private func colorFor(_ name: String?) -> Color {
        switch name {
        case "amber": return .orange
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        case "matcha", nil, "": return Color.matcha500
        default: return Color.matcha500
        }
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            journals = try await MatchaWorkService.shared.listJournals(forceRefresh: true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
