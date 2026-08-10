import SwiftUI

struct ThreadListView: View {
    let site: CappeSite

    @Environment(AppState.self) private var appState
    @State private var vm = InboxViewModel()
    @State private var showNewThread = false

    var body: some View {
        Group {
            if vm.isLoading && vm.threads.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.threads.isEmpty {
                ContentUnavailableView("No conversations yet", systemImage: "envelope")
            } else {
                List(vm.threads) { thread in
                    NavigationLink {
                        ThreadDetailView(site: site, threadId: thread.id, onRead: {
                            Task {
                                await vm.load(siteId: site.id)
                                await appState.refreshUnreadCount()
                            }
                        })
                    } label: {
                        ThreadRow(thread: thread)
                    }
                    .gummfitListRow()
                }
                .listStyle(.plain)
                .gummfitListBackground()
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Inbox")
        .gummfitScreenChrome()
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("New", systemImage: "square.and.pencil") { showNewThread = true }
            }
        }
        .sheet(isPresented: $showNewThread) {
            NavigationStack {
                NewThreadSheet(site: site, onStarted: {
                    Task {
                        await vm.load(siteId: site.id)
                        await appState.refreshUnreadCount()
                    }
                })
            }
        }
        .refreshable { await vm.load(siteId: site.id) }
        .task(id: site.id) { await vm.load(siteId: site.id) }
    }
}

private struct ThreadRow: View {
    let thread: CappeThread

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if thread.owner_unread > 0 {
                Circle().fill(GummfitTheme.accent).frame(width: 8, height: 8).padding(.top, 5)
            } else {
                Circle().fill(Color.clear).frame(width: 8, height: 8)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(thread.client_name ?? thread.client_email)
                    .font(.subheadline.bold())
                    .foregroundStyle(GummfitTheme.textPrimary)
                if let snippet = thread.last_snippet {
                    Text(snippet).font(.caption).foregroundStyle(GummfitTheme.textDim).lineLimit(1)
                }
            }
            Spacer()
        }
    }
}
