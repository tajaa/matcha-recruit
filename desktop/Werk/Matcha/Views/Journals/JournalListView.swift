import SwiftUI
import AppKit

/// Sidebar list of journals visible to the current user. Selection writes
/// `appState.selectedJournalId` and clears other selection slots so
/// ContentView routes to JournalDetailView. Refreshes on
/// `journalsListGeneration` bumps from sibling views (NewJournalSheet).
struct JournalListView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    var showHeader: Bool = true
    var searchText: String = ""

    @State private var journals: [MWJournal] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    /// Sidebar shows a few at a time; "Show more" reveals the next batch.
    @State private var visibleCount = 3
    private let pageSize = 3

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

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
                let filtered = journals.filter { j in
                    // Bypass recency when searching so old journals remain findable.
                    let passesRecency = !searchText.isEmpty || isRecentlyActive(j.updatedAt)
                    let passesSearch = searchText.isEmpty || j.title.localizedCaseInsensitiveContains(searchText)
                    return passesRecency && passesSearch
                }
                // While searching, show all matches; otherwise paginate.
                let limit = searchText.isEmpty ? visibleCount : filtered.count
                LazyVStack(spacing: 0) {
                    ForEach(filtered.prefix(limit)) { j in
                        row(j)
                    }
                    if searchText.isEmpty && filtered.count > visibleCount {
                        SidebarShowMoreButton(
                            remaining: filtered.count - visibleCount,
                            pageSize: pageSize
                        ) { visibleCount += pageSize }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .background(Color.clear)
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
                        .foregroundColor(appState.themeText.opacity(0.9))
                        .lineLimit(1)
                    if let n = j.entryCount, n > 0 {
                        Text("\(n) entr\(n == 1 ? "y" : "ies")")
                            .font(.system(size: 9))
                            .foregroundColor(appState.themeTextSecondary)
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
        .contextMenu {
            Button {
                openWindow(id: "aux", value: AuxWindowTarget.journal(j.id))
            } label: {
                Label("Open in new window", systemImage: "macwindow.on.rectangle")
            }
            Divider()
            Button("Archive") {
                Task {
                    try? await JournalService.shared.archiveJournal(id: j.id)
                    await MainActor.run {
                        if appState.selectedJournalId == j.id { appState.selectedJournalId = nil }
                        appState.journalsListGeneration &+= 1
                    }
                    await load()
                }
            }
            Divider()
            Button("Delete…") {
                let alert = NSAlert()
                alert.messageText = "Delete \"\(j.title)\"?"
                alert.informativeText = "Permanently deletes the journal and all its entries. Cannot be undone."
                alert.alertStyle = .critical
                alert.addButton(withTitle: "Delete Permanently")
                alert.addButton(withTitle: "Cancel")
                if alert.runModal() == .alertFirstButtonReturn {
                    Task {
                        try? await JournalService.shared.deleteJournal(id: j.id)
                        await MainActor.run {
                            if appState.selectedJournalId == j.id { appState.selectedJournalId = nil }
                            appState.journalsListGeneration &+= 1
                        }
                        await load()
                    }
                }
            }
        }
    }

    /// Map the stored color name to a SwiftUI Color. Free-form column on
    /// the backend; constrain client-side so the picker stays sane.
    private func colorFor(_ name: String?) -> Color {
        switch name {
        case "amber": return .orange
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        case "matcha", nil, "": return appState.themeAccent
        default: return appState.themeAccent
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
