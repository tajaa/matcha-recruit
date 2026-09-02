import Foundation
import SwiftUI
import AppKit

// MARK: - Global WebSocket handlers
//
// Split out of AppState.swift, where all three blocks were inlined into
// `didLogin` and torn down field-by-field in `didLogout`.
//
// These must be installed globally and persist across view changes: per-view
// wiring in ChannelDetailView would race/overwrite, since the callbacks live on
// a shared singleton and the most recently mounted view would win.

extension AppState {

    @MainActor
    func installRealtimeHandlers() {
        installChannelMessageHandler()
        installBroadcastHandlers()
        installCallHandlers()
    }

    /// Undo `installRealtimeHandlers` and leave any live session. Order matches
    /// the original teardown: drop the callbacks first, then leave.
    @MainActor
    func clearRealtimeHandlers() {
        ChannelsWebSocket.shared.onMessageGlobal = nil
        ChannelsWebSocket.shared.onBroadcastStarted = nil
        ChannelsWebSocket.shared.onBroadcastEnded = nil
        ChannelsWebSocket.shared.onBroadcastPublisherChanged = nil
        ChannelsWebSocket.shared.onBroadcastTokenGrant = nil
        Task { await BroadcastService.shared.leave() }
        ChannelsWebSocket.shared.onCallStarted = nil
        ChannelsWebSocket.shared.onCallEnded = nil
        ChannelsWebSocket.shared.onCallInvited = nil
        ChannelsWebSocket.shared.onCallParticipantsChanged = nil
        Task { await CallService.shared.leave() }
    }

    // MARK: - Channel messages

    /// Incoming channel message → unread bump, in-app chime/toast, or a macOS
    /// banner, depending on where the user actually is.
    @MainActor
    private func installChannelMessageHandler() {
        ChannelsWebSocket.shared.onMessageGlobal = { [weak self] msg in
            guard let self else { return }
            let isSelf = msg.senderId == self.currentUser?.id
            let isCurrentChannel = self.selectedChannelId == msg.channelId
            let active = self.isSceneActive
            let enabled = ChannelNotificationManager.shared.appNotificationsEnabled
            mwLog(
                "[AppState] onMessageGlobal channel=\(msg.channelId) "
                + "self=\(isSelf) current=\(isCurrentChannel) "
                + "sceneActive=\(active) enabled=\(enabled)"
            )
            // Ignore own messages — sender already sees their own send.
            guard !isSelf else { return }
            let channelName = ChannelsWebSocket.shared.roomName(for: msg.channelId) ?? "channel"
            // Frontmost is the right signal, not scenePhase: macOS leaves
            // scenePhase `.active` when Werk is merely behind another app, and
            // only flips to background once every window is minimized/hidden.
            // `NSApp.isActive` is true only when Werk is the focused app.
            let appFrontmost = NSApplication.shared.isActive

            if !isCurrentChannel {
                Task { @MainActor in
                    self.channelUnreadOverrides[msg.channelId, default: 0] += 1
                }
                // In-app chime only when Werk is frontmost — when it isn't, the
                // macOS banner below carries `.default` sound, so playing this
                // too would double up.
                if appFrontmost {
                    ChannelNotificationManager.shared.playInAppSound()
                }

                // In-app toast — pops in the top-right when the user is in Werk
                // (frontmost) but on another channel / view. When Werk isn't
                // frontmost the macOS banner below covers it instead, so we
                // don't double-cue.
                if ChannelNotificationManager.shared.appNotificationsEnabled,
                   appFrontmost {
                    mwLog("[AppState] pushing channel toast — \(msg.senderName) in \(channelName)")
                    let isAttachmentOnly =
                        msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        && !msg.attachments.isEmpty
                    Task { @MainActor in
                        ChannelToastCenter.shared.push(
                            ChannelToastCenter.Toast(
                                channelId: msg.channelId,
                                channelName: channelName,
                                senderName: msg.senderName,
                                content: msg.content,
                                isAttachmentOnly: isAttachmentOnly,
                            )
                        )
                    }
                }
            }

            // macOS banner — fires whenever Werk isn't the frontmost app
            // (minimized, hidden, or behind another window). The willPresent
            // delegate opts it into a banner+sound even if the process is
            // technically active. Stays silent only when the user is actually
            // looking at Werk (toast handles that case in-app). The global
            // app-notifications toggle in Settings still mutes everything.
            //
            // Empty-content (image-only) messages fall back to a
            // "📎 sent an attachment" body so the OS toast doesn't
            // render a blank line under the sender's name.
            if !appFrontmost
                && ChannelNotificationManager.shared.appNotificationsEnabled {
                let bodyText: String
                if msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    bodyText = msg.attachments.isEmpty ? "" : "📎 sent an attachment"
                } else {
                    bodyText = msg.content
                }
                ChannelNotificationManager.shared.post(
                    senderName: msg.senderName,
                    content: bodyText,
                    channelName: channelName,
                    channelId: msg.channelId,
                )
            }
        }
    }

    // MARK: - Broadcasts

    /// Broadcast lifecycle — a viewer in any view (or none) must react when an
    /// owner goes live.
    @MainActor
    private func installBroadcastHandlers() {
        let bsvc = BroadcastService.shared
        ChannelsWebSocket.shared.onBroadcastStarted = { event in
            mwLog("[AppState] WS broadcast.started channel=\(event.channelId)")
            Task { @MainActor in await bsvc.handleBroadcastStarted(event) }
        }
        ChannelsWebSocket.shared.onBroadcastEnded = { event in
            mwLog("[AppState] WS broadcast.ended channel=\(event.channelId)")
            Task { @MainActor in await bsvc.handleBroadcastEnded(event) }
        }
        ChannelsWebSocket.shared.onBroadcastPublisherChanged = { event in
            Task { @MainActor in bsvc.handlePublisherChanged(event) }
        }
        ChannelsWebSocket.shared.onBroadcastTokenGrant = { event in
            Task { @MainActor in
                await bsvc.handleTokenGrant(channelId: event.channelId,
                                            token: event.token,
                                            liveKitUrl: event.liveKitUrl,
                                            canPublish: event.canPublish)
            }
        }
    }

    // MARK: - Calls

    @MainActor
    private func installCallHandlers() {
        let csvc = CallService.shared
        csvc.currentUserId = currentUser?.id
        ChannelsWebSocket.shared.onCallStarted = { event in
            mwLog("[AppState] WS call.started channel=\(event.channelId)")
            Task { @MainActor in csvc.handleCallStarted(event) }
        }
        ChannelsWebSocket.shared.onCallEnded = { event in
            mwLog("[AppState] WS call.ended channel=\(event.channelId)")
            Task { @MainActor in await csvc.handleCallEnded(event) }
        }
        ChannelsWebSocket.shared.onCallInvited = { event in
            Task { @MainActor in csvc.handleCallInvited(event) }
        }
        ChannelsWebSocket.shared.onCallParticipantsChanged = { event in
            Task { @MainActor in csvc.handleParticipantsChanged(event) }
        }
    }
}
