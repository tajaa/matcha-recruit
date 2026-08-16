import SwiftUI

struct BoardManageView: View {
    let brandId: String?
    let slug: String?
    @State private var vm: BoardManageViewModel

    init(brandId: String?, slug: String? = nil) {
        self.brandId = brandId
        self.slug = slug
        _vm = State(initialValue: BoardManageViewModel(brandId: brandId, slug: slug))
    }

    private var badges: [BoardTab: Int] {
        guard let s = vm.summary else { return [:] }
        return [.requests: s.pending_requests, .held: s.held_replies, .members: s.member_count]
    }

    var body: some View {
        List {
            Section {
                ForEach(BoardTab.allCases) { tab in
                    NavigationLink {
                        BoardSectionScreen(tab: tab, slug: slug, vm: vm)
                    } label: {
                        BoardSectionRow(tab: tab, count: badges[tab])
                    }
                    .themedRow()
                }
            } footer: {
                if vm.summary?.is_active == false {
                    Text("This board is paused — members can't see new posts.")
                        .font(.interCaption).foregroundStyle(TU.textDim)
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Locals")
        .refreshable { await vm.loadSummary() }
        .task { await vm.loadSummary() }
        .task(id: slug ?? "") { vm.updateSlug(slug) }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}

// MARK: - Index row

/// Settings-style row for the Board index. NavigationLink in a List hit-tests
/// via UITableViewCell, not a drawn label — this replaces three prior custom
/// section-switcher controls (segmented Picker, HStack-of-Buttons, chip rail)
/// that each shipped a variant of the same hit-testing bug on-device. Do NOT
/// add .contentShape/.buttonStyle/a tap gesture here — that's what
/// reintroduces the bug this row exists to avoid.
private struct BoardSectionRow: View {
    let tab: BoardTab
    let count: Int?

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: tab.icon)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(TU.ember)
                .frame(width: 30, height: 30)
                .background(TU.ember.opacity(0.12),
                            in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(tab.title).font(.interBody)
                Text(tab.subtitle).font(.interCaption).foregroundStyle(TU.textDim)
            }
            Spacer(minLength: 8)
            if let count, count > 0 {
                Text("\(count)")
                    .font(.interCaption.weight(.bold)).monospacedDigit()
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(TU.ember, in: Capsule())
                    .foregroundStyle(TU.ink)
            }
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Section destination

/// Pushed screen for one Board section. Owns the load trigger, error banner,
/// plan-paused alert, and (Posts only) the compose sheet — previously all
/// hosted on the shared parent, now scoped to the section that needs them.
private struct BoardSectionScreen: View {
    let tab: BoardTab
    let slug: String?
    @Bindable var vm: BoardManageViewModel
    @State private var showCompose = false

    var body: some View {
        Group {
            switch tab {
            case .requests: JoinRequestsView(vm: vm)
            case .held: HeldRepliesView(vm: vm)
            case .posts: BoardPostsView(vm: vm)
            case .members: MembersView(vm: vm)
            case .team: TeamView(vm: vm)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .themedContainer()
        .navigationTitle(tab.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if tab == .posts {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCompose = true } label: { Image(systemName: "plus") }
                }
            }
        }
        .sheet(isPresented: $showCompose) { ComposePostSheet(vm: vm) }
        .task {
            // Atomic with loadTab — a late-arriving slug (see the `slug` doc
            // comment on BoardManageViewModel) must land before this section
            // loads, or Posts throws missingSlug on a stale nil.
            vm.updateSlug(slug)
            await vm.loadTab(tab)
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .alert("Plan paused", isPresented: $vm.planPausedAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("This brand's plan isn't active — board mutations are disabled until they reactivate.")
        }
    }
}
