import Foundation

extension AppState {
    // MARK: - Workspace tabs

    static func loadTabs() -> [WorkTab] {
        guard let data = UserDefaults.standard.data(forKey: tabsKey),
              let tabs = try? JSONDecoder().decode([WorkTab].self, from: data),
              !tabs.isEmpty
        else { return [.home] }
        // Home must always lead.
        return tabs.first?.kind == .home ? tabs : [.home] + tabs.filter { $0.kind != .home }
    }

    static func saveTabs(_ tabs: [WorkTab]) {
        if let data = try? JSONEncoder().encode(tabs) {
            UserDefaults.standard.set(data, forKey: tabsKey)
        }
    }

    var pinnedTabCount: Int { openTabs.filter { $0.kind != .home }.count }
    var canPinActiveTab: Bool {
        activeTab.kind != .home
            && !openTabs.contains(where: { $0.id == activeTab.id })
            && pinnedTabCount < AppState.maxPinnedTabs
    }

    /// Switch the detail pane to a tab's destination.
    @MainActor
    func selectTab(_ tab: WorkTab) {
        activeTab = tab
        navigateToDestination(tab)
    }

    /// Pin the currently-open item as a tab (no-op for Home / duplicates / when full).
    @MainActor
    func pinActiveTab() {
        guard canPinActiveTab else { return }
        openTabs.append(activeTab)
    }

    @MainActor
    func closeTab(_ tab: WorkTab) {
        guard tab.kind != .home else { return }
        openTabs.removeAll { $0.id == tab.id }
        if activeTab.id == tab.id { selectTab(.home) }
    }

    /// Called by a detail view once its data loads: marks it active and
    /// refreshes the cached title on any matching pinned tab.
    @MainActor
    func setActiveContext(_ tab: WorkTab) {
        activeTab = tab
        if let idx = openTabs.firstIndex(where: { $0.id == tab.id }), openTabs[idx].title != tab.title {
            openTabs[idx].title = tab.title
        }
    }

    // MARK: - Side pane

    /// Per person: the target can name their threads, journals and so on, and
    /// must never come back for whoever signs in next on this Mac.
    private var lastSideTargetKey: String? {
        currentUser.map { "mw-last-side-target-v2:\($0.id)" }
    }

    /// What the side pane showed last, so ⌘\ brings it back.
    var lastSideTarget: AuxWindowTarget {
        guard let key = lastSideTargetKey,
              let data = UserDefaults.standard.data(forKey: key),
              let target = try? JSONDecoder().decode(AuxWindowTarget.self, from: data),
              target.isRememberable
        else { return .calendar }
        return target
    }

    /// Show `target` beside whatever the main pane has open.
    @MainActor
    func openBeside(_ target: AuxWindowTarget) {
        splitTarget = target
        guard target.isRememberable, let key = lastSideTargetKey,
              let data = try? JSONEncoder().encode(target) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    /// ⌘\: close the side pane, or reopen the last one.
    @MainActor
    func toggleSidePane() {
        if splitTarget != nil {
            splitTarget = nil
        } else {
            openBeside(lastSideTarget)
        }
    }

    /// What the main pane shows, as a pane target: the open item, else the
    /// open hub. nil on Home and the other full-pane pages (inbox, people…).
    /// Same precedence as `PrimaryDetailPane`. Journals is a workspace with its
    /// own selection (`selectedJournalId` only deep-links into it), so the
    /// journal actually open there is the one it mirrors here.
    var mainPaneTarget: AuxWindowTarget? {
        if let id = selectedThreadId { return .thread(id) }
        if let id = selectedProjectId { return .project(id) }
        if let id = selectedChannelId { return .channel(id) }
        if showThreadsHub { return .threads }
        if showProjectsHub { return .workspaces }
        if showJournalsHub || selectedJournalId != nil {
            return mainJournalsSelection.map { .journal($0) } ?? .journals
        }
        if showChannelsHub { return .channels }
        if showProductivityHub { return .kanban }
        if showCalendarHub { return .calendar }
        if showEmailHub { return .email }
        if showAssistantHub { return .assistant }
        return nil
    }

    /// Navigate the main pane to `target` (a file opens the preview sheet).
    @MainActor
    func showInMain(_ target: AuxWindowTarget) {
        if case .file(let ref) = target {
            globalPreviewFile = ref.asProjectFile
            return
        }
        clearPrimaryNav()
        switch target {
        case .project(let id): selectedProjectId = id
        case .channel(let id): selectedChannelId = id
        case .thread(let id): selectedThreadId = id
        case .journal(let id): selectedJournalId = id
        case .calendar: showCalendarHub = true
        case .journals: showJournalsHub = true
        case .kanban: showProductivityHub = true
        case .assistant: showAssistantHub = true
        case .channels: showChannelsHub = true
        case .threads: showThreadsHub = true
        case .email: showEmailHub = true
        case .workspaces: showProjectsHub = true
        case .file: break
        }
    }

    /// A calendar link followed from `pane`: in the main pane it opens the
    /// Calendar there; in a side pane it opens it in that pane, so the main
    /// pane keeps what it had.
    @MainActor
    func openCalendar(at date: Date? = nil, in pane: WorkPane) {
        guard pane.isSide else { openCalendar(at: date); return }
        paneCalendarFocusDate = date
        pane.open(.calendar)
    }

    /// An email link followed from `pane`, routed like `openCalendar(at:in:)`.
    @MainActor
    func openEmail(id: String, in pane: WorkPane) {
        guard pane.isSide else { openEmail(id: id); return }
        panePendingEmailId = id
        pane.open(.email)
    }

    @MainActor
    private func navigateToDestination(_ tab: WorkTab) {
        selectedProjectId = nil
        selectedThreadId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        showEmailHub = false
        showAssistantHub = false
        showCalendarHub = false
        showHome = false
        showSkills = false
        showInbox = false
        showPeople = false
        showChannelBrowse = false
        switch tab.kind {
        case .home: showHome = true
        case .project: selectedProjectId = tab.entityId
        case .channel: selectedChannelId = tab.entityId
        case .thread: selectedThreadId = tab.entityId
        case .journal: selectedJournalId = tab.entityId
        }
    }

}
