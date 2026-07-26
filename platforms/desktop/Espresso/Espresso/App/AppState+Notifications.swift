import Foundation
import UserNotifications
import SwiftUI
import AppKit

// MARK: - Notifications: the bell, toasts, permission, and deep links
//
// Split out of AppState.swift.

extension AppState {

    // MARK: - Observers

    /// macOS banner clicks (relayed by AppDelegate, which can't reach this
    /// SwiftUI-owned instance directly) → deep-link to the notification's
    /// target via handleNotificationLink.
    func subscribeBannerTapObserver() {
        bannerTapTask?.cancel()
        bannerTapTask = Task { @MainActor [weak self] in
            for await note in NotificationCenter.default.notifications(named: .mwNotificationBannerTapped) {
                guard let self else { break }
                let link = note.userInfo?["link"] as? String
                var metadata: [String: String]? = nil
                if let raw = note.userInfo?["metadata"] as? [String: Any] {
                    metadata = raw.reduce(into: [String: String]()) { acc, kv in
                        if let s = kv.value as? String { acc[kv.key] = s }
                    }
                }
                if link != nil || metadata != nil {
                    self.handleNotificationLink(link, metadata: metadata)
                }
            }
        }
    }

    /// Wire the `.mwNewNotification` push fan-out — fired by ChannelsWebSocket
    /// when the server pushes a `notification` event. Bumps the bell count,
    /// reconciles via a single REST refetch (handles missed pushes during
    /// reconnect), and fires a macOS UNNotification toast for non-channel
    /// types (channel-chat toasts still go through the starred-channel path
    /// in onMessageGlobal to avoid double-notifying).
    @MainActor
    func subscribeNewNotificationObserver() {
        newNotificationTask?.cancel()
        // Async-sequence form: a directly-created @MainActor task iterating the
        // notifications avoids the @Sendable block of the token-based observer
        // closing over non-Sendable `self` (the Swift-6 capture warning).
        newNotificationTask = Task { @MainActor [weak self] in
            for await note in NotificationCenter.default.notifications(named: .mwNewNotification) {
                guard let self else { break }
                let n = note.userInfo?["notification"] as? [String: Any]
                // Awaited, not fire-and-forget: the loop serializes on the
                // count refetch exactly as the inlined version did, so two
                // notifications arriving back-to-back can't race two refreshes.
                await self.handlePushedNotification(n)
            }
        }
    }

    /// One pushed `notification` payload: badge, per-project count, and
    /// whichever toast (in-app or OS) fits where the user currently is.
    @MainActor
    private func handlePushedNotification(_ n: [String: Any]?) async {
        let type = n?["type"] as? String ?? ""
        let isChannel = type.hasPrefix("channel_")
        let meta = AppState.metadataDict(n?["metadata"])
        func metaString(_ key: String) -> String? { meta[key] }

        // Bell badge ticks for every notification type so kanban moves,
        // channel messages, mentions all show up. Refresh from server to
        // stay in sync if the user dismissed something on another device.
        notificationsUnreadCount += 1
        await refreshNotificationsCount()
        NotificationCenter.default.post(name: .mwNotificationsRefresh, object: nil)

        // Per-project tab badge: any notification carrying a project_id
        // bumps that project's unseen count. Bumps even when the user is
        // in the project — the badge clears only when they open the
        // specific ticket/note, not on opening the project tab.
        if let pid = metaString("project_id"), !pid.isEmpty {
            projectUnseenCounts[pid, default: 0] += 1
        }

        // "X joined the collab" → in-app toast when the user is looking
        // at Werk (the bell already ticked; the OS banner below covers
        // the not-frontmost case).
        if type == "collab_joined", NSApplication.shared.isActive {
            let joiner = metaString("joiner_name") ?? "Someone"
            let proj = metaString("project_title") ?? (n?["title"] as? String ?? "the collab")
            ChannelToastCenter.shared.push(
                ChannelToastCenter.Toast(
                    channelId: "",
                    channelName: proj,
                    senderName: joiner,
                    content: "joined the collab",
                    isAttachmentOnly: false
                )
            )
        }

        // Cross-project kanban/ticket activity → in-app toast when the
        // user is looking at Werk, so a change in ANOTHER project can
        // pull their attention over. Skipped when they're already in
        // that project (the project WS path toasts those live — see
        // ProjectDetailViewModel — so this would double up).
        if ["task_progress", "task_assigned", "task_rejected", "task_comment"].contains(type),
           NSApplication.shared.isActive {
            let pid = metaString("project_id") ?? ""
            if !pid.isEmpty, pid != selectedProjectId {
                let projTitle = metaString("project_title")
                    ?? (n?["title"] as? String ?? "Workspace")
                let msg = (n?["body"] as? String) ?? (n?["title"] as? String ?? "Updated")
                ChannelNotificationManager.shared.playInAppSound()
                WorkToastCenter.shared.push(
                    WorkToastCenter.Toast(
                        projectId: pid,
                        projectTitle: projTitle,
                        message: msg,
                        systemImage: AppState.ticketToastIcon(type)
                    )
                )
            }
        }

        // "X started an audio call" → in-app toast when the user is
        // looking at Werk but not already in that channel (the channel
        // view shows its own join banner). Clicking lands them in the
        // channel via the toast's channelId.
        if type == "call_started", NSApplication.shared.isActive {
            let cid = metaString("channel_id") ?? ""
            if !cid.isEmpty, cid != selectedChannelId {
                ChannelNotificationManager.shared.playInAppSound()
                ChannelToastCenter.shared.push(
                    ChannelToastCenter.Toast(
                        channelId: cid,
                        channelName: metaString("channel_name") ?? "channel",
                        senderName: metaString("actor_name") ?? "Someone",
                        content: "started an audio call — click to join",
                        isAttachmentOnly: false
                    )
                )
            }
        }

        // OS toast is owned by the starred-channel path in
        // `onMessageGlobal` for channel_* events — skip those here to
        // avoid double-toasting on chat. Non-channel events
        // (task_assigned, mentions, collab_joined, call_started, …)
        // get it here, carrying link+metadata so a banner click
        // deep-links to the target.
        if !isSceneActive && !isChannel {
            var userInfo: [AnyHashable: Any] = [:]
            if let link = n?["link"] as? String, !link.isEmpty {
                userInfo["link"] = link
            }
            if !meta.isEmpty { userInfo["metadata"] = meta }
            ChannelNotificationManager.shared.postSystem(
                title: n?["title"] as? String ?? "Notification",
                body: n?["body"] as? String,
                userInfo: userInfo.isEmpty ? nil : userInfo
            )
        }
    }

    /// A pushed notification's `metadata` arrives either as a dict or as a JSON
    /// string, so the string form must be decoded before any key read.
    ///
    /// Two hand-written copies of this decode used to sit in the same function
    /// — one inside a per-key lookup helper, one building the banner userInfo —
    /// which meant the JSON was re-parsed on *every* key read (up to five per
    /// notification), plus once more for the banner.
    private static func metadataDict(_ raw: Any?) -> [String: String] {
        var out: [String: String] = [:]
        if let d = raw as? [String: Any] {
            for (k, v) in d { if let s = v as? String { out[k] = s } }
        } else if let s = raw as? String, let data = s.data(using: .utf8),
                  let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            for (k, v) in d { if let sv = v as? String { out[k] = sv } }
        }
        return out
    }

    private static func ticketToastIcon(_ type: String) -> String {
        switch type {
        case "task_assigned": return "person.crop.circle.badge.checkmark"
        case "task_rejected": return "arrow.uturn.backward"
        case "task_comment": return "bubble.left.fill"
        default: return "arrow.left.arrow.right"
        }
    }

    // MARK: - Permission prompt

    /// Surface the notification-permission prompt on every app open when
    /// status is anything other than `.authorized`. macOS only shows the
    /// OS dialog once per install, so the in-app alert is the only way to
    /// nudge denied / provisional / ephemeral users. The user can mute the
    /// alert permanently via "Don't ask again".
    /// Called from both `didLogin` (cold launch: restoreSession → didLogin
    /// completes after scenePhase fires, so onSceneActive's early-return
    /// would otherwise miss the check) and `onSceneActive` (warm reopen).
    @MainActor
    func promptForNotificationsIfNeeded() {
        guard !ChannelNotificationManager.shared.promptSuppressed else { return }
        ChannelNotificationManager.shared.checkAuthorizationStatus { [weak self] status in
            guard let self else { return }
            switch status {
            case .authorized:
                return
            case .notDetermined:
                // First-ever launch: fire OS dialog only. The in-app alert
                // would double-nag legitimate users who immediately click
                // Allow. If macOS Focus/MDM/DND suppresses the OS dialog,
                // the next scene activation reads back .denied and the
                // alert fires then.
                ChannelNotificationManager.shared.requestPermission()
            default:
                // .denied, .provisional, .ephemeral — all show the alert
                self.showNotificationReprompt = true
            }
        }
    }

    // MARK: - Counters

    @MainActor
    func clearChannelUnread(_ channelId: String) {
        channelUnreadOverrides.removeValue(forKey: channelId)
        channelUnreadCounts[channelId] = 0
        // Being in the channel = seen. Drop its channel notifications from the
        // bell too, so the bell and the channel tab badge stay in lock-step.
        Task {
            try? await MatchaWorkService.shared.markNotificationsReadBy(channelId: channelId)
            await self.refreshNotificationsCount()
        }
    }

    /// Force a refetch of the unread count — used by the notifications popover
    /// after a mark-read or mark-all-read action so the badge updates without
    /// waiting for the next poll tick.
    @MainActor
    func refreshNotificationsCount() async {
        if let count = try? await MatchaWorkService.shared.fetchNotificationsUnreadCount() {
            notificationsUnreadCount = count
        }
    }

    /// Server-authoritative refetch of the per-project tab badge counts.
    @MainActor
    func refreshProjectUnseenCounts() async {
        if let counts = try? await MatchaWorkService.shared.fetchProjectUnreadCounts() {
            projectUnseenCounts = counts
        }
    }

    /// Unseen count for a tab chip. Projects roll up unread notifications;
    /// channels reuse the channel unread (server seed + live WS overrides).
    /// Home/thread/journal have no per-entity read state → no badge.
    @MainActor
    func tabUnread(_ tab: WorkTab) -> Int {
        switch tab.kind {
        case .project:
            return projectUnseenCounts[tab.entityId] ?? 0
        case .channel:
            return (channelUnreadCounts[tab.entityId] ?? 0) + (channelUnreadOverrides[tab.entityId] ?? 0)
        case .home, .thread, .journal:
            return 0
        }
    }

    /// User opened a ticket → clear its notifications from the bell + project
    /// tab badge. Per-entity clear: opening the project tab does nothing; only
    /// opening the specific ticket dismisses it.
    @MainActor
    func markTicketSeen(taskId: String) {
        Task {
            try? await MatchaWorkService.shared.markNotificationsReadBy(taskId: taskId)
            await self.refreshProjectUnseenCounts()
            await self.refreshNotificationsCount()
        }
    }

    /// User opened a note section → clear its comment notifications.
    @MainActor
    func markSectionSeen(sectionId: String) {
        Task {
            try? await MatchaWorkService.shared.markNotificationsReadBy(sectionId: sectionId)
            await self.refreshProjectUnseenCounts()
            await self.refreshNotificationsCount()
        }
    }

    // MARK: - Deep links

    /// Navigate to the object a notification points at. Most notifications
    /// carry the target in `metadata` (project_id / task_id / thread_id /
    /// channel_id / journal_id) with a bare `/work` link; task notifications
    /// also encode it in the link query (`?project=&task=`). We prefer
    /// metadata and fall back to the link query, so either shape navigates.
    /// Mirrors the surface-clearing the sidebar / home buttons do.
    @MainActor
    func handleNotificationLink(_ link: String?, metadata: [String: String]? = nil) {
        // Never navigate from a notification while signed out. macOS keeps
        // banners across logout, so a banner posted in user A's session could
        // otherwise be tapped after user B signs in on the same Mac and drive
        // B to A's entity id. Ownership of the id is still enforced server-side
        // on fetch; this stops the cross-session navigation at the door.
        guard isAuthenticated else { return }
        // Link query params (if any).
        let items = link.flatMap { URLComponents(string: $0)?.queryItems } ?? []
        func query(_ key: String) -> String? {
            items.first(where: { $0.name == key })?.value.flatMap { $0.isEmpty ? nil : $0 }
        }
        func meta(_ key: String) -> String? {
            metadata?[key].flatMap { $0.isEmpty ? nil : $0 }
        }
        // Prefer metadata's `<thing>_id`, fall back to link's `<thing>`.
        func target(_ name: String) -> String? { meta("\(name)_id") ?? query(name) }

        let project = target("project")
        let task = target("task")
        let thread = target("thread")
        let channel = target("channel")
        let journal = target("journal")

        func clearSurfaces() {
            showHome = false
            showSkills = false
            showInbox = false
            showPeople = false
            showChannelBrowse = false
            selectedEmailId = nil
        }

        if let project {
            clearSurfaces()
            selectedThreadId = nil
            selectedJournalId = nil
            selectedChannelId = nil
            selectedProjectId = project
            // A task notification should land on the kanban board, not chat.
            pendingProjectPanel = task != nil ? .kanban : nil
        } else if let thread {
            clearSurfaces()
            selectedProjectId = nil
            selectedJournalId = nil
            selectedChannelId = nil
            selectedThreadId = thread
        } else if let channel {
            clearSurfaces()
            selectedProjectId = nil
            selectedThreadId = nil
            selectedJournalId = nil
            selectedChannelId = channel
        } else if let journal {
            clearSurfaces()
            selectedProjectId = nil
            selectedThreadId = nil
            selectedChannelId = nil
            selectedJournalId = journal
        }
    }
}
