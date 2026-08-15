import SwiftUI

/// Auto-dismissing error banner. `message` is set by the caller's VM; the
/// banner clears its own local state (not the VM's) on dismiss so a re-tap
/// of the same action can re-show the same error. Dismisses itself after 5s
/// or on tap.
struct ErrorBanner: View {
    let message: String?
    @State private var dismissed = false

    var body: some View {
        if let message, !message.isEmpty, !dismissed {
            Text(message)
                .font(.interFootnote)
                .foregroundStyle(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.red, in: Capsule())
                .transition(.move(edge: .top).combined(with: .opacity))
                .onTapGesture { dismissed = true }
                .task(id: message) {
                    dismissed = false
                    try? await Task.sleep(for: .seconds(5))
                    dismissed = true
                }
        }
    }
}
