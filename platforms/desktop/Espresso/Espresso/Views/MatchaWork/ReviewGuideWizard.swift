import SwiftUI

/// Skippable how-to for the review → complete-ticket workflow. Shown once per
/// install on first collab-board open (UserDefaults `werk-review-wizard-seen`),
/// and re-openable from the board's "?" button. Themed (works in light /
/// cappuchin / dark).
struct ReviewGuideWizard: View {
    @Environment(AppState.self) private var appState
    var onClose: () -> Void

    static let seenKey = "werk-review-wizard-seen"

    @State private var step = 0

    private struct Page { let icon: String; let title: String; let body: String }
    private let pages: [Page] = [
        Page(icon: "rectangle.stack.fill",
             title: "Tickets move through rounds",
             body: "Each ticket flows Todo → In Progress → Review → Done. Sending one back from review opens a new ROUND, so each rework pass reads as its own block in the history."),
        Page(icon: "arrow.triangle.branch",
             title: "Commits check off the work",
             body: "Merge to main and the scanner reads your commits. A confident match auto-checks the subtask; a borderline one shows a ✨ suggestion chip you Accept with one tap. Nothing is ever flipped without a record."),
        Page(icon: "checkmark.seal.fill",
             title: "Review: keep or deny each item",
             body: "Open a ticket in Review. Each done item shows which commit completed it (and how sure the AI was). If it isn't really done, hit the ✗ Deny, choose Blocker or Nit, and say why — it reopens and rolls into the next round."),
        Page(icon: "arrow.uturn.backward.circle.fill",
             title: "Send back, or approve",
             body: "Send back → the ticket goes to Changes Requested with your denials listed for the assignee. Approve → it moves to Done with a sign-off. On a re-review, “Since last review” shows only what changed this round."),
    ]

    private var page: Page { pages[step] }
    private var isLast: Bool { step == pages.count - 1 }

    var body: some View {
        VStack(spacing: 0) {
            // Header: progress dots + skip
            HStack {
                HStack(spacing: 5) {
                    ForEach(0..<pages.count, id: \.self) { i in
                        Circle()
                            .fill(i == step ? appState.themeAccent : appState.themeText.opacity(0.18))
                            .frame(width: 6, height: 6)
                    }
                }
                Spacer()
                Button("Skip") { finish() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .padding(.horizontal, 20).padding(.top, 16)

            Spacer(minLength: 0)

            VStack(spacing: 14) {
                Image(systemName: page.icon)
                    .font(.system(size: 34))
                    .foregroundColor(appState.themeAccent)
                    .frame(height: 40)
                Text(page.title)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .multilineTextAlignment(.center)
                Text(page.body)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.75))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 360)
            }
            .padding(.horizontal, 28)

            Spacer(minLength: 0)

            // Footer: Back / Next or Done
            HStack {
                Button("Back") { withAnimation { step -= 1 } }
                    .buttonStyle(.plain).font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .opacity(step == 0 ? 0 : 1)
                    .disabled(step == 0)
                Spacer()
                Button {
                    if isLast { finish() } else { withAnimation { step += 1 } }
                } label: {
                    Text(isLast ? "Got it" : "Next")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(appState.themeOnAccent)
                        .padding(.horizontal, 18).padding(.vertical, 7)
                        .background(appState.themeAccent)
                        .cornerRadius(7)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20).padding(.bottom, 16)
        }
        .frame(width: 460, height: 360)
        .background(appState.themeBg)
    }

    private func finish() {
        UserDefaults.standard.set(true, forKey: Self.seenKey)
        onClose()
    }
}
