import SwiftUI

struct FriendsGuideView: View {
    let onFindFriends: () -> Void
    let onInvite: () -> Void
    let onDone: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var stepIndex = 0
    @State private var didExit = false

    private let steps = [
        (
            icon: "person.2.fill",
            eyebrow: "1 · Find your people",
            title: "Search or browse suggestions",
            body: "Find someone by name or @handle, or let Tell-Us suggest people based on shared places, boards, and your city. Send a request, then become friends when they accept."
        ),
        (
            icon: "qrcode",
            eyebrow: "2 · Invite by QR",
            title: "Share a friend invite",
            body: "Tap the QR button in Friends to create your invite. Share the link or code, and your friend can scan or paste it to connect instantly."
        ),
        (
            icon: "newspaper.fill",
            eyebrow: "3 · Keep up",
            title: "See what friends discover",
            body: "Friend activity brings published reviews and followed places into one feed. Open any friend to see the profile sections they choose to share."
        ),
        (
            icon: "lock.shield.fill",
            eyebrow: "4 · Stay in control",
            title: "Choose what people see",
            body: "Use Settings to control profile visibility, search discoverability, and leaderboard sharing. You can also block or report an account from its profile."
        ),
    ]

    private var current: (icon: String, eyebrow: String, title: String, body: String) {
        steps[stepIndex]
    }

    private var isLast: Bool { stepIndex == steps.count - 1 }

    private func finish() {
        didExit = true
        onDone()
    }

    private func findFriends() {
        didExit = true
        onFindFriends()
    }

    private func invite() {
        didExit = true
        onInvite()
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                ProgressView(value: Double(stepIndex + 1), total: Double(steps.count))
                    .tint(TU.ember)

                Image(systemName: current.icon)
                    .font(.system(size: 42, weight: .semibold))
                    .foregroundStyle(TU.ember)
                    .frame(width: 84, height: 84)
                    .background(TU.ember.opacity(0.14), in: RoundedRectangle(cornerRadius: 22))

                VStack(spacing: 8) {
                    Text(current.eyebrow)
                        .font(TU.eyebrow())
                        .foregroundStyle(TU.emberHot)
                    Text(current.title)
                        .font(.interTitle3.bold())
                        .multilineTextAlignment(.center)
                    Text(current.body)
                        .font(.interBody)
                        .foregroundStyle(TU.textDim)
                        .multilineTextAlignment(.center)
                }

                Spacer()

                HStack(spacing: 10) {
                    if stepIndex > 0 {
                        Button("Back") { stepIndex -= 1 }
                            .buttonStyle(.bordered)
                    }
                    Spacer()
                    if stepIndex == 0 {
                        Button("Find friends") { findFriends() }
                            .buttonStyle(EmberButtonStyle())
                    } else if stepIndex == 1 {
                        Button("Share invite") { invite() }
                            .buttonStyle(EmberButtonStyle())
                    }
                    Button(isLast ? "Finish" : "Next") {
                        if isLast {
                            finish()
                        } else {
                            stepIndex += 1
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(TU.ember)
                }
            }
            .padding()
            .navigationTitle("Friends, in four moves")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Skip") { finish(); dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .onDisappear {
            if !didExit { finish() }
        }
    }
}
