import SwiftUI

struct MessagesListView: View {
    let scope: InboxScope
    @Environment(\.scenePhase) private var scenePhase
    @State private var vm: DmThreadsViewModel

    init(scope: InboxScope = .consumer) {
        self.scope = scope
        _vm = State(initialValue: DmThreadsViewModel(scope: scope))
    }

    var body: some View {
        Group {
            if vm.threads.isEmpty && !vm.isLoading {
                EmptyState(icon: "message", title: "No messages yet")
            } else {
                List(vm.threads) { thread in
                    NavigationLink {
                        DmThreadView(vm: DmThreadViewModel(thread: thread))
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(thread.counterparty_name).font(.interHeadline)
                                HStack(spacing: 6) {
                                    Text(thread.kind == .feedback ? "Feedback" : (thread.topic?.label ?? "Question"))
                                    if let store = thread.store_name { Text("· \(store)") }
                                }
                                .font(.interCaption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text(Formatters.relativeString(from: thread.last_message_at))
                                    .font(.interCaption2).foregroundStyle(.secondary)
                                if thread.unread_count > 0 {
                                    Text("\(thread.unread_count)")
                                        .font(.interCaption2.bold())
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(.red, in: Capsule())
                                        .foregroundStyle(.white)
                                }
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle(scope == .consumer ? "Comms" : "Business inbox")
        .task {
            await vm.load()
            vm.startPolling()
        }
        .onDisappear { vm.stopPolling() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { vm.startPolling() } else { vm.stopPolling() }
        }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
