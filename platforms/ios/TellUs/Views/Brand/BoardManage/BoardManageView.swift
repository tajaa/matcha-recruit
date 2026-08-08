import SwiftUI

struct BoardManageView: View {
    let brandId: String?
    @State private var vm: BoardManageViewModel
    @State private var tab = 0
    @State private var showCompose = false

    init(brandId: String?) {
        self.brandId = brandId
        _vm = State(initialValue: BoardManageViewModel(brandId: brandId))
    }

    var body: some View {
        VStack(spacing: 0) {
            if let summary = vm.summary {
                HStack {
                    Label("\(summary.pending_requests)", systemImage: "person.badge.clock")
                    Label("\(summary.held_replies)", systemImage: "checkmark.bubble")
                    Label("\(summary.member_count)", systemImage: "person.3")
                }
                .font(.footnote)
                .padding(.horizontal)
                .padding(.top, 4)
            }

            Picker("", selection: $tab) {
                Text("Requests").tag(0)
                Text("Held").tag(1)
                Text("Posts").tag(2)
                Text("Members").tag(3)
            }
            .pickerStyle(.segmented)
            .padding()

            Group {
                switch tab {
                case 0: JoinRequestsView(vm: vm)
                case 1: HeldRepliesView(vm: vm)
                case 2: postsPlaceholder
                default: MembersView(vm: vm)
                }
            }
        }
        .navigationTitle("Board")
        .toolbar {
            if tab == 2 {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCompose = true } label: { Image(systemName: "plus") }
                }
            }
        }
        .sheet(isPresented: $showCompose) { ComposePostSheet(vm: vm) }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .alert("Plan paused", isPresented: $vm.planPausedAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("This brand's plan isn't active — board mutations are disabled until they reactivate.")
        }
    }

    private var postsPlaceholder: some View {
        EmptyState(icon: "square.and.pencil", title: "Compose a post", hint: "Use the + button above.")
    }
}
