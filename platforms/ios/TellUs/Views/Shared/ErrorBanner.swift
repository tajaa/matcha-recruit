import SwiftUI

/// Auto-dismissing error banner. `message` is set by the caller's VM; the
/// banner clears its own state (not the VM's) on dismiss so a re-tap of the
/// same action can re-show the same error.
struct ErrorBanner: View {
    let message: String?

    var body: some View {
        if let message, !message.isEmpty {
            Text(message)
                .font(.footnote)
                .foregroundStyle(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.red, in: Capsule())
                .transition(.move(edge: .top).combined(with: .opacity))
        }
    }
}
