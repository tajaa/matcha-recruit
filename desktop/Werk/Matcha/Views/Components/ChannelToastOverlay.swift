import SwiftUI

/// In-app banner that surfaces inbound channel messages. Sits in the
/// top-right corner above all views; stacks up to 3 toasts; auto-dismisses
/// each after 5s. Tap a toast to jump into the channel. Driven by
/// `ChannelToastCenter.shared` which AppState pushes into from the
/// global channels-WS message handler.
@Observable
final class ChannelToastCenter {
    static let shared = ChannelToastCenter()

    struct Toast: Identifiable, Equatable {
        let id = UUID()
        let channelId: String
        let channelName: String
        let senderName: String
        let content: String
        /// True when the source message has attachments but no text. Used
        /// to swap an empty content body for an "📎 sent an attachment"
        /// hint so the toast doesn't render a blank line.
        let isAttachmentOnly: Bool

        /// Text rendered for the body. Falls back to an attachment hint
        /// when the message itself was attachment-only.
        var displayContent: String {
            if content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return isAttachmentOnly ? "📎 sent an attachment" : ""
            }
            return content
        }
    }

    private(set) var toasts: [Toast] = []

    /// Toast IDs the user is currently hovering. Paused toasts skip the
    /// auto-dismiss so a long read isn't yanked away mid-sentence.
    private var hoveredIds: Set<UUID> = []

    /// Push a toast onto the stack. Newest renders at the top. Older
    /// toasts pushed off the bottom when count exceeds 3.
    @MainActor
    func push(_ t: Toast) {
        toasts.insert(t, at: 0)
        if toasts.count > 3 {
            toasts = Array(toasts.prefix(3))
        }
        let id = t.id
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(5))
            if !hoveredIds.contains(id) {
                dismiss(id: id)
            } else {
                // User is hovering — re-arm a longer timer once they
                // move away. The hover-end path triggers the second
                // dismiss attempt.
            }
        }
    }

    @MainActor
    func setHover(_ id: UUID, _ hovering: Bool) {
        if hovering {
            hoveredIds.insert(id)
        } else {
            hoveredIds.remove(id)
            // Restart a short timer after hover ends so the toast still
            // disappears eventually.
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                if !hoveredIds.contains(id) {
                    dismiss(id: id)
                }
            }
        }
    }

    @MainActor
    func dismiss(id: UUID) {
        toasts.removeAll { $0.id == id }
    }

    @MainActor
    func dismissAll() {
        toasts.removeAll()
    }

    private init() {}
}

struct ChannelToastOverlay: View {
    @Environment(AppState.self) private var appState
    @State private var center = ChannelToastCenter.shared

    var body: some View {
        VStack(alignment: .trailing, spacing: 8) {
            ForEach(center.toasts) { toast in
                ChannelToastView(toast: toast) {
                    appState.selectedChannelId = toast.channelId
                    appState.showInbox = false
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedJournalId = nil
                    appState.clearChannelUnread(toast.channelId)
                    center.dismiss(id: toast.id)
                } onDismiss: {
                    center.dismiss(id: toast.id)
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }
            Spacer()
        }
        .padding(.top, 40)            // clears the title bar
        .padding(.trailing, 16)
        .frame(maxWidth: .infinity, alignment: .topTrailing)
        .allowsHitTesting(!center.toasts.isEmpty)
        .animation(.easeInOut(duration: 0.2), value: center.toasts)
    }
}

private struct ChannelToastView: View {
    let toast: ChannelToastCenter.Toast
    let onTap: () -> Void
    let onDismiss: () -> Void
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.fill")
                    .font(.system(size: 10))
                    .foregroundColor(Color.matcha500)
                Text("#\(toast.channelName)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                        .padding(4)
                }
                .buttonStyle(.plain)
            }
            Text(toast.senderName)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.white)
            if !toast.displayContent.isEmpty {
                Text(toast.displayContent)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.85))
                    .lineLimit(2)
            }
        }
        .padding(10)
        .frame(width: 280, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.zinc900.opacity(0.95))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isHovered ? Color.matcha500 : Color.matcha500.opacity(0.4),
                                lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.3), radius: 12, x: 0, y: 4)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            isHovered = hovering
            ChannelToastCenter.shared.setHover(toast.id, hovering)
        }
        .onTapGesture(perform: onTap)
    }
}

// ---------------------------------------------------------------------------
// Work activity toasts — collaborator kanban/ticket changes in real time.
// Mirrors ChannelToastCenter (stack of 3, 5s auto-dismiss, hover-to-hold) but
// taps jump to the *project* rather than a channel. Pushed from
// ProjectDetailViewModel's task.* WS handlers for non-self actors.
// ---------------------------------------------------------------------------

@Observable
final class WorkToastCenter {
    static let shared = WorkToastCenter()

    struct Toast: Identifiable, Equatable {
        let id = UUID()
        let projectId: String
        let projectTitle: String
        let message: String        // e.g. "Haley moved 'Fix login' to In Review"
        let systemImage: String    // SF Symbol for the leading icon
    }

    private(set) var toasts: [Toast] = []
    private var hoveredIds: Set<UUID> = []

    @MainActor
    func push(_ t: Toast) {
        toasts.insert(t, at: 0)
        if toasts.count > 3 {
            toasts = Array(toasts.prefix(3))
        }
        let id = t.id
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(5))
            if !hoveredIds.contains(id) { dismiss(id: id) }
        }
    }

    @MainActor
    func setHover(_ id: UUID, _ hovering: Bool) {
        if hovering {
            hoveredIds.insert(id)
        } else {
            hoveredIds.remove(id)
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                if !hoveredIds.contains(id) { dismiss(id: id) }
            }
        }
    }

    @MainActor func dismiss(id: UUID) { toasts.removeAll { $0.id == id } }
    @MainActor func dismissAll() { toasts.removeAll() }

    private init() {}
}

struct WorkToastOverlay: View {
    @Environment(AppState.self) private var appState
    @State private var center = WorkToastCenter.shared

    var body: some View {
        VStack(alignment: .trailing, spacing: 8) {
            Spacer()
            ForEach(center.toasts) { toast in
                WorkToastView(toast: toast) {
                    // Jump to the project; the collab layout defaults to the
                    // kanban panel so the user lands on the board.
                    appState.selectedProjectId = toast.projectId
                    appState.showInbox = false
                    appState.selectedThreadId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    center.dismiss(id: toast.id)
                } onDismiss: {
                    center.dismiss(id: toast.id)
                }
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .padding(.bottom, 16)
        .padding(.trailing, 16)
        .frame(maxWidth: .infinity, alignment: .bottomTrailing)
        .allowsHitTesting(!center.toasts.isEmpty)
        .animation(.easeInOut(duration: 0.2), value: center.toasts)
    }
}

private struct WorkToastView: View {
    let toast: WorkToastCenter.Toast
    let onTap: () -> Void
    let onDismiss: () -> Void
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: toast.systemImage)
                    .font(.system(size: 10))
                    .foregroundColor(Color.matcha500)
                Text(toast.projectTitle)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Spacer()
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                        .padding(4)
                }
                .buttonStyle(.plain)
            }
            Text(toast.message)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.85))
                .lineLimit(2)
        }
        .padding(10)
        .frame(width: 280, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.zinc900.opacity(0.95))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isHovered ? Color.matcha500 : Color.matcha500.opacity(0.4),
                                lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.3), radius: 12, x: 0, y: 4)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            isHovered = hovering
            WorkToastCenter.shared.setHover(toast.id, hovering)
        }
        .onTapGesture(perform: onTap)
    }
}
