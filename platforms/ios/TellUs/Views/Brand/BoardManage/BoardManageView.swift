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

            BoardTabBar(selection: $tab)
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
        .task(id: tab.rawValue.description + ":" + (slug ?? "")) {
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

/// Plain-SwiftUI tab strip — not `Picker(.segmented)`. That's a UIKit
/// `UISegmentedControl` bridge whose per-segment tap regions get out of sync
/// with the app's custom Inter font environment override on real devices
/// (fine in the simulator, unresponsive on-device with 5 tight segments).
/// Same shape as `SignupView.accountTypeSwitch`/`typeButton`.
private struct BoardTabBar: View {
    @Binding var selection: BoardTab

    var body: some View {
        HStack(spacing: 4) {
            ForEach(BoardTab.allCases) { tab in
                let selected = selection == tab
                Button {
                    selection = tab
                } label: {
                    Text(tab.title)
                        .font(.interCaption.weight(selected ? .semibold : .medium))
                        .foregroundStyle(selected ? TU.ink : TU.textDim)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background {
                            if selected {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(TU.ember)
                            }
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .background(TU.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(TU.hairline, lineWidth: 1)
        )
    }
}
