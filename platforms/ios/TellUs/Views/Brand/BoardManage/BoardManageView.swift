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

    /// Counts folded into the rail's chips — the standalone icon row they used
    /// to live in duplicated information the tabs already imply.
    private var badges: [BoardTab: Int] {
        guard let s = vm.summary else { return [:] }
        return [.requests: s.pending_requests, .held: s.held_replies, .members: s.member_count]
    }

    var body: some View {
        VStack(spacing: 0) {
            BoardTabRail(selection: $tab, badges: badges)
                .padding(.top, 4)
                .padding(.bottom, 10)

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


// MARK: - Tab rail

/// Scrolling chip rail. Third shape this control has taken, so the reasons
/// matter:
///
/// 1. `Picker(.segmented)` bridges to UIKit's `UISegmentedControl` — its
///    per-segment tap regions desynced from layout on-device.
/// 2. The HStack-of-Buttons that replaced it laid the segments out with
///    `.frame(maxWidth: .infinity)` over a bare `Text` and no `contentShape`.
///    SwiftUI hit-tests a button's *drawn* label, not the layout frame it was
///    offered, so every unselected chip only answered taps that landed on the
///    glyphs themselves (the selected one worked — it had a fill behind it).
///    A simulator click is pixel-exact so it always hit; a fingertip centroid
///    lands in the dead padding. The segments were also ~32pt tall, under the
///    44pt HIG minimum.
///
/// So: every chip is `.frame(height: 44)` + `.contentShape(Rectangle())`
/// applied *after* padding, which makes the whole pill — fill or not —
/// hittable. Five chips no longer have to share one screen width, so the
/// labels get real horizontal padding instead of being squeezed to 65pt.
private struct BoardTabRail: View {
    @Binding var selection: BoardTab
    var badges: [BoardTab: Int]

    private let haptic = UISelectionFeedbackGenerator()

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(BoardTab.allCases) { tab in
                        chip(tab).id(tab)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 2)
            }
            .scrollBounceBehavior(.basedOnSize, axes: .horizontal)
            .onChange(of: selection) { _, new in
                withAnimation(.easeOut(duration: 0.22)) { proxy.scrollTo(new, anchor: .center) }
            }
        }
    }

    private func chip(_ tab: BoardTab) -> some View {
        let selected = selection == tab
        let count = badges[tab] ?? 0
        return Button {
            guard selection != tab else { return }
            haptic.selectionChanged()
            withAnimation(.easeOut(duration: 0.18)) { selection = tab }
        } label: {
            HStack(spacing: 6) {
                Text(tab.title)
                    .font(.interSubheadline.weight(selected ? .semibold : .medium))
                    .lineLimit(1)
                if count > 0 {
                    Text("\(count)")
                        .font(.interCaption2.weight(.bold))
                        .monospacedDigit()
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            selected ? TU.ink.opacity(0.20) : TU.ember.opacity(0.20),
                            in: Capsule()
                        )
                }
            }
            .foregroundStyle(selected ? TU.ink : TU.textDim)
            .padding(.horizontal, 16)
            .frame(height: 44)
            .background {
                Capsule()
                    .fill(selected ? AnyShapeStyle(TU.ember) : AnyShapeStyle(TU.surface))
            }
            .overlay {
                Capsule().strokeBorder(selected ? .clear : TU.hairline, lineWidth: 1)
            }
            // Applied last, so the full pill — padding included — hit-tests.
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(count > 0 ? "\(tab.title), \(count)" : tab.title)
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
    }
}
