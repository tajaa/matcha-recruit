import SwiftUI

struct MessagesListView: View {
    @State private var vm = DmThreadsViewModel()

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
                                Text(thread.counterparty_name).font(.headline)
                                if let title = thread.report_title {
                                    Text(title).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                Text(Formatters.relativeString(from: thread.last_message_at))
                                    .font(.caption2).foregroundStyle(.secondary)
                                if thread.unread_count > 0 {
                                    Text("\(thread.unread_count)")
                                        .font(.caption2.bold())
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
        .navigationTitle("Messages")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
