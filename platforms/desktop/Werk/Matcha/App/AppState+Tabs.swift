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

    @MainActor
    private func navigateToDestination(_ tab: WorkTab) {
        selectedProjectId = nil
        selectedThreadId = nil
        selectedChannelId = nil
        selectedJournalId = nil
        selectedEmailId = nil
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

    /// Navigate to the object a notification points at. Most notifications
}
