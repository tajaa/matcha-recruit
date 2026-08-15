import SwiftUI

struct BoardManageView: View {
    let brandId: String?
    let slug: String?
    @State private var vm: BoardManageViewModel
    @State private var tab: BoardTab = .requests
    @State private var showCompose = false

    init(brandId: String?, slug: String? = nil) {
        self.brandId = brandId
        self.slug = slug
        _vm = State(initialValue: BoardManageViewModel(brandId: brandId, slug: slug))
    }

    var body: some View {
        VStack(spacing: 0) {
            if let summary = vm.summary {
                HStack {
                    Label("\(summary.pending_requests)", systemImage: "person.badge.clock")
                    Label("\(summary.held_replies)", systemImage: "checkmark.bubble")
                    Label("\(summary.member_count)", systemImage: "person.3")
                }
                .font(.interFootnote)
                .foregroundStyle(TU.textDim)
                .padding(.horizontal)
                .padding(.top, 4)
            }

            Picker("", selection: $tab) {
                ForEach(BoardTab.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)
            .tint(TU.ember)
            .padding()

            Group {
                switch tab {
                case .requests: JoinRequestsView(vm: vm)
                case .held: HeldRepliesView(vm: vm)
                case .posts: BoardPostsView(vm: vm)
                case .members: MembersView(vm: vm)
                case .team: TeamView(vm: vm)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .themedContainer()
        .navigationTitle("Board")
        .toolbar {
            if tab == .posts {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCompose = true } label: { Image(systemName: "plus") }
                }
            }
        }
        .sheet(isPresented: $showCompose) { ComposePostSheet(vm: vm) }
        .task { await vm.loadSummary() }
        .onAppear {
            vm.updateSlug(slug)
            Task { await vm.loadTab(tab) }
        }
        .onChange(of: tab) { _, newTab in
            Task { await vm.loadTab(newTab) }
        }
        .onChange(of: slug) { _, newSlug in
            vm.updateSlug(newSlug)
            Task { await vm.loadTab(tab) }
        }
        .refreshable { await vm.refresh(tab) }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .alert("Plan paused", isPresented: $vm.planPausedAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("This brand's plan isn't active — board mutations are disabled until they reactivate.")
        }
    }
}
