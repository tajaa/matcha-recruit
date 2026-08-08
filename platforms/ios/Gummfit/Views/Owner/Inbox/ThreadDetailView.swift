import SwiftUI

struct ThreadDetailView: View {
    let site: CappeSite
    let threadId: String
    var onRead: () -> Void = {}

    @State private var vm = ThreadViewModel()
    @State private var draft = ""

    var body: some View {
        VStack(spacing: 0) {
            ErrorBanner(message: vm.error)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(vm.thread?.messages ?? []) { message in
                        MessageBubble(message: message)
                    }
                }
                .padding()
            }
            Divider()
            HStack {
                TextField("Reply…", text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("Send") {
                    Task {
                        let body = draft
                        draft = ""
                        await vm.reply(siteId: site.id, body: body)
                    }
                }
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.isSending)
            }
            .padding()
        }
        .navigationTitle(vm.thread?.client_name ?? vm.thread?.client_email ?? "Conversation")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if let token = vm.thread?.access_token,
                   let url = SafeURL.validated("\(APIClient.shared.webOrigin)/cappe/thread/\(token)") {
                    Link(destination: url) {
                        Image(systemName: "link")
                    }
                }
                if vm.thread?.status == "open" {
                    Button("Close") { Task { await vm.close(siteId: site.id) } }
                }
            }
        }
        .task {
            await vm.load(siteId: site.id, threadId: threadId)
            onRead()
        }
    }
}

private struct MessageBubble: View {
    let message: CappeMessage

    var isOwner: Bool { message.sender == "owner" }

    var body: some View {
        HStack {
            if isOwner { Spacer() }
            Text(message.body)
                .padding(10)
                .background(isOwner ? GummfitTheme.accent.opacity(0.2) : Color.gray.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
            if !isOwner { Spacer() }
        }
    }
}
