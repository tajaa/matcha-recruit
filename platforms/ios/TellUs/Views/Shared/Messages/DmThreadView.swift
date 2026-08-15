import SwiftUI

struct DmThreadView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.scenePhase) private var scenePhase
    @Bindable var vm: DmThreadViewModel
    @State private var draft = ""
    @State private var showBlockConfirm = false
    @State private var showCloseConfirm = false
    @State private var team: [BrandTeamMember] = []

    private var isConsumer: Bool {
        vm.thread?.viewer_role == .consumer ||
        (vm.thread?.viewer_role == nil && appState.account?.account_type == .consumer)
    }

    var body: some View {
        ScrollViewReader { proxy in
            List {
                ForEach(vm.messages) { message in
                    DmBubbleRow(message: message)
                        .id(message.id)
                        .listRowSeparator(.hidden)
                }
            }
            .listStyle(.plain)
            .onChange(of: vm.messages.count) { _, _ in
                if let last = vm.messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
        .safeAreaInset(edge: .bottom) {
            if !vm.canCompose {
                Text(vm.thread?.status == .closed
                     ? "This conversation is closed."
                     : "This conversation has ended.")
                    .font(.interFootnote).foregroundStyle(.secondary)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(.bar)
            } else {
                HStack {
                    TextField("Message…", text: $draft)
                        .textFieldStyle(.roundedBorder)
                    Button("Send") {
                        Task {
                            let toSend = draft
                            draft = ""
                            await vm.send(toSend)
                        }
                    }
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.isSending)
                }
                .padding()
                .background(.bar)
            }
        }
        .navigationTitle(vm.thread?.counterparty_name ?? "Message")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            // Only the consumer side can block/unblock a brand thread.
            if isConsumer, vm.thread != nil {
                ToolbarItem(placement: .topBarTrailing) {
                    if vm.thread?.blocked == true {
                        Button("Unblock") { Task { await vm.unblock() } }
                    } else {
                        Button("Block", role: .destructive) { showBlockConfirm = true }
                    }
                }
            }
            if !isConsumer, vm.thread?.status != .closed {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        if vm.thread?.assigned_member_id == nil {
                            Button("Take conversation") { Task { await vm.take() } }
                        }
                        if !team.isEmpty {
                            Divider()
                            ForEach(team.filter(\.can_manage_inbox)) { member in
                                Button("Assign to (member.account_display_name)") {
                                    Task { await vm.assign(to: member.id) }
                                }
                            }
                            if vm.thread?.assigned_member_id != nil {
                                Button("Unassign") { Task { await vm.assign(to: nil) } }
                            }
                        }
                        Button("Close conversation", role: .destructive) { showCloseConfirm = true }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
        .confirmationDialog("Block this conversation?", isPresented: $showBlockConfirm, titleVisibility: .visible) {
            Button("Block", role: .destructive) { Task { await vm.block() } }
        }
        .confirmationDialog("Close this conversation?", isPresented: $showCloseConfirm, titleVisibility: .visible) {
            Button("Close", role: .destructive) { Task { await vm.close() } }
        }
        .task {
            await vm.load()
            if appState.account?.account_type == .brand {
                team = (try? await BoardManageService.shared.team(brandId: nil)) ?? []
            }
            vm.startPolling()
        }
        .onDisappear { vm.stopPolling() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { vm.startPolling() } else { vm.stopPolling() }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}

/// Split out of DmThreadView's ForEach body — the ternary-laden background/
/// foregroundStyle/Spacer chain inline defeated the type-checker (same class
/// of issue documented for ReportDetailForm's Sections).
private struct DmBubbleRow: View {
    let message: DmMessage

    var body: some View {
        HStack {
            if message.is_mine { Spacer(minLength: 40) }
            Text(message.body)
                .padding(10)
                .background(bubbleColor, in: RoundedRectangle(cornerRadius: 12))
                .foregroundStyle(textColor)
            if !message.is_mine { Spacer(minLength: 40) }
        }
    }

    private var bubbleColor: Color {
        message.is_mine ? Color.accentColor : Color(.secondarySystemBackground)
    }

    private var textColor: Color {
        message.is_mine ? .white : .primary
    }
}
