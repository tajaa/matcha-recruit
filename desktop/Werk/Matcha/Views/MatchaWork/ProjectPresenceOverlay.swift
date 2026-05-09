import SwiftUI

/// Wraps a content view with mouse-tracking + remote-cursor rendering.
/// The wrapped view's coordinate space defines (xPct=0, yPct=0) at the
/// top-left and (1, 1) at the bottom-right; coords are sent to the server
/// in this normalized space so cross-screen-size doesn't matter.
///
/// `.onContinuousHover` is the macOS 13+ equivalent of an NSEvent local
/// monitor scoped to a SwiftUI view — fires per-pixel while the pointer
/// is in the bounds, automatically released when the view leaves the
/// hierarchy. The presence VM throttles outgoing sends to 50ms.
struct ProjectPresenceOverlay<Content: View>: View {
    let presenceVM: ProjectPresenceViewModel
    let members: [ProjectWebSocket.PresenceMember]
    @ViewBuilder let content: () -> Content

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            content()
                .onContinuousHover(coordinateSpace: .local) { phase in
                    guard size.width > 0, size.height > 0 else { return }
                    switch phase {
                    case .active(let p):
                        presenceVM.reportCursor(
                            xPct: p.x / size.width,
                            yPct: p.y / size.height,
                        )
                    case .ended:
                        // Send a sentinel out-of-bounds value so peers can hide
                        // our cursor when we leave the area. Peers that didn't
                        // get the message just see the cursor freeze at the
                        // last-known position — acceptable in v1.
                        presenceVM.reportCursor(xPct: 1.5, yPct: 1.5)
                    }
                }
                .overlay(remoteCursorsOverlay(size: size))
        }
    }

    private func remoteCursorsOverlay(size: CGSize) -> some View {
        // Use the live remoteCursors map. Lookup name from the members list
        // so a stale cursor (sender left without a `user_left`) still renders
        // until the next presence snapshot — non-blocking edge case.
        ZStack(alignment: .topLeading) {
            ForEach(Array(presenceVM.remoteCursors.keys), id: \.self) { userId in
                if let cur = presenceVM.remoteCursors[userId],
                   cur.xPct >= 0, cur.xPct <= 1, cur.yPct >= 0, cur.yPct <= 1 {
                    let name = members.first(where: { $0.id == userId })?.name ?? "…"
                    let color = UserColor.forUserId(userId)
                    cursorMarker(name: name, color: color)
                        .position(
                            x: cur.xPct * size.width,
                            y: cur.yPct * size.height,
                        )
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func cursorMarker(name: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            // SF Symbol "cursorarrow" is the closest match to the system
            // pointer; tinted to the user's stable color so each remote
            // cursor reads as a distinct individual on a busy section.
            Image(systemName: "cursorarrow.rays")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(color)
            Text(name)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.white)
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(color)
                .cornerRadius(3)
        }
        .offset(x: 4, y: 4)
    }
}
