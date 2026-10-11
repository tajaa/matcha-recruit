import SwiftUI

// MARK: - Pane context

/// Where a view is being shown. The main pane owns the window's navigation
/// (`selected*Id`, the hub flags); a side pane, the bottom pane or an aux
/// window shows something beside it and must leave that alone. Hubs read this
/// to switch to their pane layout and to send their own links into the pane.
struct WorkPane {
    var isSide = false
    /// Open a target from inside a side pane: it replaces what the pane shows
    /// (Back returns). Unused in the main pane, where hubs navigate as before.
    var open: (AuxWindowTarget) -> Void = { _ in }
}

private struct WorkPaneKey: EnvironmentKey {
    static let defaultValue = WorkPane()
}

extension EnvironmentValues {
    var workPane: WorkPane {
        get { self[WorkPaneKey.self] }
        set { self[WorkPaneKey.self] = newValue }
    }
}

// MARK: - Main-pane rails

extension View {
    /// Fold a hub's rail while a side pane is open, so the item open in the
    /// main pane keeps its room. `folded` is the hub's temporary fold, shown
    /// on top of its own collapsed setting and never written into it; the
    /// person can still unfold the rail while the pane is open.
    func foldsRailForSidePane(_ folded: Binding<Bool>) -> some View {
        modifier(SidePaneRailFold(folded: folded))
    }
}

private struct SidePaneRailFold: ViewModifier {
    @Binding var folded: Bool
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var pane

    func body(content: Content) -> some View {
        content
            .onAppear { sync(paneOpen: appState.splitTarget != nil) }
            .onChange(of: appState.splitTarget != nil) { _, open in sync(paneOpen: open) }
    }

    private func sync(paneOpen: Bool) {
        guard !pane.isSide else { return }
        folded = paneOpen
    }
}

// MARK: - Side pane

/// A pane beside the main one: the right split or the bottom split. One view
/// for both so they behave alike: a dock to flip between surfaces, Back after
/// opening something inside the pane, swap with the main pane, move to the
/// other edge, pop out, close. The body renders via AuxWindowRootView in pane
/// mode, so it never writes the main pane's navigation.
struct SidePane: View {
    enum Slot { case right, bottom }

    let slot: Slot
    let target: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    @State private var history: [AuxWindowTarget] = []
    /// Set while the pane moves itself (open inside, Back), so a target change
    /// from anywhere else (the dock, ⌘F, a context menu) starts history over.
    @State private var navigating = false
    @State private var titles = SplitSwitcherModel()

    var body: some View {
        VStack(spacing: 0) {
            SidePaneHeader(
                slot: slot,
                target: target,
                canGoBack: !history.isEmpty,
                titles: titles,
                onBack: back,
                onPick: { show($0) },
                onSwap: swapWithMain,
                onMove: moveToOtherEdge,
                onPopOut: popOut,
                onClose: { show(nil) }
            )
            Divider().opacity(0.2)
            AuxWindowRootView(target: target)
                .environment(\.workPane, WorkPane(isSide: true, open: push))
        }
        .task { await titles.loadIfNeeded() }
        .onChange(of: target) { _, _ in
            if navigating { navigating = false } else { history = [] }
        }
    }

    private func show(_ next: AuxWindowTarget?) {
        switch slot {
        case .right:
            if let next { appState.openBeside(next) } else { appState.splitTarget = nil }
        case .bottom:
            appState.bottomSplitTarget = next
        }
    }

    private func push(_ next: AuxWindowTarget) {
        guard next != target else { return }
        history.append(target)
        navigating = true
        show(next)
        Task { await titles.loadIfNeeded() }
    }

    private func back() {
        guard let previous = history.popLast() else { return }
        navigating = true
        show(previous)
    }

    /// Put this pane's content in the main pane and what the main pane had
    /// here. With nothing open in the main pane the pane just moves over.
    private func swapWithMain() {
        let main = appState.mainPaneTarget
        appState.showInMain(target)
        show(main)
    }

    private func moveToOtherEdge() {
        switch slot {
        case .right:
            let other = appState.bottomSplitTarget
            appState.bottomSplitTarget = target
            appState.splitTarget = other
        case .bottom:
            let other = appState.splitTarget
            appState.openBeside(target)
            appState.bottomSplitTarget = other
        }
    }

    private func popOut() {
        openWindow(id: "aux", value: target)
        show(nil)
    }
}

// MARK: - Header

/// The pane's header: Back, the surface dock, what is open, and the pane
/// actions. The dock collapses into a menu when the pane is too narrow for it.
private struct SidePaneHeader: View {
    let slot: SidePane.Slot
    let target: AuxWindowTarget
    let canGoBack: Bool
    let titles: SplitSwitcherModel
    let onBack: () -> Void
    let onPick: (AuxWindowTarget) -> Void
    let onSwap: () -> Void
    let onMove: () -> Void
    let onPopOut: () -> Void
    let onClose: () -> Void
    @Environment(AppState.self) private var appState

    private var dock: [AuxWindowTarget] {
        AuxWindowTarget.dock(assistantEnabled: appState.assistantEnabled)
    }

    var body: some View {
        HStack(spacing: 6) {
            if canGoBack {
                PaneIconButton(icon: "chevron.left", help: "Back", action: onBack)
            }
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) {
                    dockStrip
                    itemTitle
                }
                HStack(spacing: 6) {
                    dockMenu
                    itemTitle
                }
                dockMenu
            }
            Spacer(minLength: 4)
            PaneIconButton(icon: "arrow.left.arrow.right", help: "Swap with the main pane", action: onSwap)
            PaneIconButton(
                icon: slot == .right ? "rectangle.split.1x2" : "rectangle.split.2x1",
                help: slot == .right ? "Move to the bottom" : "Move to the side",
                action: onMove
            )
            PaneIconButton(icon: "macwindow.on.rectangle", help: "Pop out to a window", action: onPopOut)
            PaneIconButton(icon: "xmark", help: slot == .right ? "Close side pane (⌘\\)" : "Close bottom pane", action: onClose)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(appState.themeText.opacity(0.025))
    }

    private var dockStrip: some View {
        HStack(spacing: 2) {
            ForEach(Array(dock.enumerated()), id: \.offset) { index, surface in
                DockButton(
                    surface: surface,
                    isActive: target.surface == surface,
                    help: slot == .right && index < 9
                        ? "\(surface.surfaceName) (⌥⌘\(index + 1))"
                        : surface.surfaceName
                ) { onPick(surface) }
            }
        }
        .padding(2)
        .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(0.04)))
    }

    private var dockMenu: some View {
        Menu {
            ForEach(Array(dock.enumerated()), id: \.offset) { _, surface in
                Button { onPick(surface) } label: {
                    Label(surface.surfaceName, systemImage: surface.icon)
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: (target.surface ?? target).icon)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                Text(target.surfaceName)
                    .font(.espresso(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Show something else here")
    }

    /// The open item's name (a surface needs none: the dock already says it).
    @ViewBuilder
    private var itemTitle: some View {
        if !target.isSurface {
            Text(titles.title(for: target))
                .font(.espresso(size: 11, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
                .lineLimit(1)
                .truncationMode(.tail)
                .fixedSize()
        }
    }
}

private struct DockButton: View {
    let surface: AuxWindowTarget
    let isActive: Bool
    let help: String
    let action: () -> Void
    @Environment(AppState.self) private var appState
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: surface.icon)
                .font(.system(size: 11, weight: isActive ? .semibold : .regular))
                .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                .frame(width: 26, height: 22)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isActive
                              ? appState.themeAccent.opacity(0.14)
                              : appState.themeText.opacity(hovering ? 0.07 : 0))
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help(help)
        .accessibilityLabel(surface.surfaceName)
    }
}

struct PaneIconButton: View {
    let icon: String
    let help: String
    let action: () -> Void
    @Environment(AppState.self) private var appState
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 24, height: 22)
                .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeText.opacity(hovering ? 0.07 : 0)))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help(help)
    }
}

// MARK: - Toolbar button

/// The window toolbar's way in: click to show or hide the side pane (the last
/// surface it had), or pick which surface to put there.
struct SidePaneToolbarButton: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Menu {
            ForEach(Array(AuxWindowTarget.dock(assistantEnabled: appState.assistantEnabled).enumerated()),
                    id: \.offset) { _, surface in
                Button { appState.openBeside(surface) } label: {
                    Label(surface.surfaceName, systemImage: surface.icon)
                }
            }
            Divider()
            Button("Find anything to open beside… (⌘F)") { appState.showFinderPalette = true }
            if appState.splitTarget != nil {
                Button("Close side pane") { appState.splitTarget = nil }
            }
        } label: {
            Image(systemName: appState.splitTarget == nil ? "rectangle.split.2x1" : "rectangle.split.2x1.fill")
                .font(.system(size: 13))
                .foregroundColor(appState.splitTarget == nil ? appState.themeText.opacity(0.7) : appState.themeAccent)
        } primaryAction: {
            appState.toggleSidePane()
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help(appState.splitTarget == nil
              ? "Open \(appState.lastSideTarget.surfaceName) beside (⌘\\) · hold for more"
              : "Close side pane (⌘\\)")
    }
}

// MARK: - List surfaces

/// Threads, channels, journals or workspaces in a side pane: a searchable list
/// whose rows open the item in the same pane (Back returns to the list). The
/// full hubs are three-column layouts that need the whole window.
struct SidePaneList: View {
    let surface: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var pane
    @State private var model = SplitSwitcherModel()
    @State private var loaded = false
    @State private var search = ""
    @FocusState private var searchFocused: Bool

    private struct Row: Identifiable {
        let id: String
        let target: AuxWindowTarget
        let title: String
        let detail: String?
        let icon: String
        let sortKey: String
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                TextField("Search \(surface.surfaceName.lowercased())", text: $search)
                    .textFieldStyle(.plain)
                    .font(.espresso(size: 12))
                    .foregroundColor(appState.themeText)
                    .focused($searchFocused)
                    .onSubmit { if let first = rows.first { pane.open(first.target) } }
                if !search.isEmpty {
                    Button { search = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(0.05)))
            .padding(10)

            if !loaded {
                ProgressView().controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if rows.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: surface.icon)
                        .font(.system(size: 24))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.6))
                    Text(search.isEmpty ? "No \(surface.surfaceName.lowercased()) yet" : "No matches")
                        .font(.espresso(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(rows) { row in
                            SidePaneListRow(icon: row.icon, title: row.title, detail: row.detail) {
                                pane.open(row.target)
                            }
                            .contextMenu { AuxOpenMenuButtons(target: row.target) }
                        }
                    }
                    .padding(.horizontal, 8).padding(.bottom, 10)
                }
            }
        }
        .background(ThemeRadialBackground())
        .task {
            await model.load()
            loaded = true
        }
    }

    private var rows: [Row] {
        var out: [Row]
        switch surface {
        case .threads:
            out = model.threads.map {
                Row(id: $0.id, target: .thread($0.id), title: $0.displayName,
                    detail: PacificDateFormatter.relative($0.lastActivityAt),
                    icon: $0.resolvedTaskType.icon, sortKey: $0.lastActivityAt)
            }
        case .channels:
            out = model.channels.map {
                Row(id: $0.id, target: .channel($0.id), title: "#\($0.name)",
                    detail: $0.lastMessagePreview ?? PacificDateFormatter.relative($0.lastMessageAt),
                    icon: "number", sortKey: $0.lastMessageAt ?? "")
            }
        case .journals:
            out = model.journals.map {
                Row(id: $0.id, target: .journal($0.id), title: $0.title,
                    detail: PacificDateFormatter.relative($0.updatedAt ?? $0.createdAt),
                    icon: $0.icon ?? "book.closed", sortKey: $0.updatedAt ?? $0.createdAt ?? "")
            }
        case .workspaces:
            out = model.projects.map {
                Row(id: $0.id, target: .project($0.id), title: $0.title, detail: $0.status?.capitalized,
                    icon: $0.icon ?? "square.grid.2x2", sortKey: "")
            }
        default:
            out = []
        }
        // Most recent first; workspaces keep the server's order.
        if surface != .workspaces {
            out.sort { $0.sortKey > $1.sortKey }
        }
        let q = search.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return out }
        return out.filter {
            $0.title.localizedCaseInsensitiveContains(q)
                || ($0.detail?.localizedCaseInsensitiveContains(q) ?? false)
        }
    }
}

private struct SidePaneListRow: View {
    let icon: String
    let title: String
    let detail: String?
    let action: () -> Void
    @Environment(AppState.self) private var appState
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                    .frame(width: 26, height: 26)
                    .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeAccent.opacity(0.12)))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title.isEmpty ? "Untitled" : title)
                        .font(.espresso(size: 12, weight: .medium))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                    if let detail, !detail.isEmpty {
                        Text(detail)
                            .font(.espresso(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary.opacity(hovering ? 0.9 : 0.4))
            }
            .padding(.horizontal, 8).padding(.vertical, 7)
            .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(hovering ? 0.06 : 0)))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}
