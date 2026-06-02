import SwiftUI

/// Passthrough wrapper, kept so call sites stay stable.
///
/// It used to broadcast each person's *mouse-pointer* position (via
/// `.onContinuousHover`) and draw a floating `cursorarrow` for every remote
/// collaborator. That "whole-app cursor" was noise — what you actually want is
/// to see where someone is *in the document*, which the caret-presence system
/// now renders in-text (see `MarkdownTextEditor.remoteCarets` + the read-only
/// watcher in `SectionEditorView`). So the mouse-cursor capture + overlay are
/// gone; this just renders its content.
struct ProjectPresenceOverlay<Content: View>: View {
    let presenceVM: ProjectPresenceViewModel
    let members: [ProjectWebSocket.PresenceMember]
    @ViewBuilder let content: () -> Content

    var body: some View {
        content()
    }
}
