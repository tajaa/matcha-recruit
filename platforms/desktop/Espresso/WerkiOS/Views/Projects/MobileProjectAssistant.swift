import SwiftUI

/// Project-scoped AI threads use the same saved conversations and streaming
/// recovery path as desktop. Selecting an existing thread never creates one.
struct MobileProjectAssistant: View {
    let projectId: String
    @State private var threads: [MWThread] = []
    @State private var selected: MWThread?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        List {
            Section {
                Button("Start a conversation", systemImage: "sparkles") {
                    guard !busy else { return }
                    busy = true
                    Task {
                        defer { busy = false }
                        do {
                            let thread = try await MatchaWorkService.shared.createProjectChat(projectId: projectId)
                            threads.insert(thread, at: 0); selected = thread
                        } catch { self.error = error.localizedDescription }
                    }
                }.disabled(busy)
                Text("Think through an idea, write a first draft, or ask about your project. Conversations follow their existing desktop sharing permissions.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Section("Your conversations") {
                if busy { ProgressView() }
                ForEach(threads) { thread in
                    Button { selected = thread } label: {
                        HStack {
                            Image(systemName: "bubble.left").foregroundStyle(EspressoStyle.accent)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(thread.displayName == "(UNNAMED)" ? "New conversation" : thread.displayName).foregroundStyle(.primary)
                                Text(PacificDateFormatter.relative(thread.lastActivityAt) ?? "").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if (thread.collaboratorCount ?? 0) > 0 { EspressoBadge(text: "Shared") }
                        }
                    }
                }
            }
        }.scrollContentBackground(.hidden).espressoBackground()
            .task { await load() }.refreshable { await load() }
            .sheet(item: $selected, onDismiss: { Task { await load() } }) { MobileAssistantThread(threadId: $0.id) }
            .espressoError($error)
    }
    private func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do { threads = try await MatchaWorkService.shared.listProjectChats(projectId: projectId) }
        catch { self.error = error.localizedDescription }
    }
}

private struct MobileAssistantThread: View {
    let threadId: String
    @Environment(\.dismiss) private var dismiss
    @State private var vm: ThreadDetailViewModel
    @State private var draft = ""
    @State private var sending = false
    init(threadId: String) {
        self.threadId = threadId
        _vm = State(initialValue: WorkDetailVMStore.shared.threadVM(threadId))
    }
    var body: some View {
        NavigationStack {
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        if vm.isLoadingThread { ProgressView() }
                        if vm.messages.isEmpty && !vm.isLoadingThread {
                            EspressoEmptyState(title: "A fresh perspective", message: "What are you working on?", symbol: "sparkles")
                        }
                        ForEach(vm.messages) { message in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(message.role == "user" ? "You" : "Espresso").font(.caption.weight(.semibold)).foregroundStyle(EspressoStyle.accent)
                                Text(.init(message.content)).textSelection(.enabled)
                            }.frame(maxWidth: .infinity, alignment: .leading).espressoCard()
                        }
                        if vm.isStreaming {
                            VStack(alignment: .leading, spacing: 8) {
                                Label("Espresso", systemImage: "sparkles").font(.caption.weight(.semibold))
                                if vm.streamingContent.isEmpty { ProgressView() }
                                else { Text(.init(vm.streamingContent)).textSelection(.enabled) }
                            }.espressoCard()
                        }
                        if let error = vm.errorMessage { Text(error).font(.footnote).foregroundStyle(.red) }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(20)
                }.onChange(of: vm.messages.count) { _, _ in scroll.scrollTo("bottom", anchor: .bottom) }
            }
            .espressoBackground()
            .safeAreaInset(edge: .bottom) {
                HStack(alignment: .bottom, spacing: 12) {
                    TextField("Ask Espresso…", text: $draft, axis: .vertical).lineLimit(1...6)
                        .padding(14).espressoSurface(cornerRadius: 22)
                    if vm.isStreaming {
                        Button("Stop", systemImage: "stop.circle.fill") { vm.cancelStreaming() }.labelStyle(.iconOnly).font(.title).frame(width: 44, height: 44)
                    } else {
                        Button("Send", systemImage: "arrow.up.circle.fill") { send() }.labelStyle(.iconOnly).font(.title).frame(width: 44, height: 44)
                            .disabled(sending || vm.thread == nil || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }.padding(16).background(.bar)
            }
            .navigationTitle("Espresso").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Done") { vm.cancelStreaming(); dismiss() } }
            .task { await vm.loadThread(id: threadId) }
            .onDisappear { vm.cancelStreaming() }
        }.tint(EspressoStyle.accent)
    }
    private func send() {
        guard !sending && !vm.isStreaming else { return }
        let content = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return }
        sending = true; draft = ""
        Task {
            defer { sending = false }
            guard await AuthService.shared.refreshIfNeeded() else {
                vm.errorMessage = "Couldn't refresh your session. Your draft is still here; check your connection and try again."
                if draft.isEmpty { draft = content }
                return
            }
            await vm.sendMessage(content: content)
            // Do not automatically re-send: a failed stream may have persisted
            // the message already. The shared VM reloads its server state.
        }
    }
}
