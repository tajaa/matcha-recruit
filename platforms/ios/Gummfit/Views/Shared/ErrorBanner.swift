import SwiftUI

/// Auto-dismissing error banner. `message` is set by the caller's VM; the
/// banner clears its own local state (not the VM's) on dismiss so a re-tap
/// of the same action can re-show the same error. Dismisses itself after 5s
/// or on tap.
struct ErrorBanner: View {
    let message: String?
    @State private var dismissed = false

    var body: some View {
        Group {
            if let message, !message.isEmpty, !dismissed {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.red, in: Capsule())
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .onTapGesture { dismissed = true }
                    .task {
                        try? await Task.sleep(for: .seconds(5))
                        dismissed = true
                    }
            }
        }
        // Lives outside the `if` (which unmounts once dismissed, taking any
        // reset logic attached to the Text with it) so a NEW message after
        // dismissal — even a repeat of the same string, since callers clear
        // `error` to nil between attempts (LoadableVM.withLoad) — always
        // clears `dismissed` and re-shows the banner.
        .onChange(of: message) { dismissed = false }
    }
}
