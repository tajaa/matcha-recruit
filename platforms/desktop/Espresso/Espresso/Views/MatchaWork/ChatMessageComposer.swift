import SwiftUI

/// The message composer for `ChatPanelView`.
///
/// Mirrors `ChannelMessageComposer`'s contract, and for the same reason: the
/// live draft is **local `@State`**, so typing re-renders only this view rather
/// than `ChatPanelView.body` — which holds the whole message list in the same
/// body. Keeping the draft on the parent meant every keystroke rebuilt the
/// `ScrollView`/`LazyVStack`/`ForEach` descriptors and re-evaluated every
/// realized `MessageBubbleView`, which is what made typing stall on long
/// threads and large drafts.
struct ChatMessageComposer: View {
    @Environment(AppState.self) private var appState

    let placeholder: String
    /// Matches server-side `SendMessageRequest.content` Field(max_length=…).
    let charLimit: Int
    let isStreaming: Bool
    let isUploadingImages: Bool
    /// External prefill/clear. When `seedNonce` changes the composer copies
    /// `seed` into its local `text` — used to clear after a send and to fill
    /// from a suggestion card, without binding the field to parent state on
    /// every keystroke.
    let seed: String
    let seedNonce: Int
    /// The draft is passed up because the composer owns it locally.
    let onSend: (String) -> Void
    let onPickFiles: () -> Void

    @State private var text: String = ""
    /// Maintained once per edit rather than recomputed several times per body
    /// evaluation. The trim+grapheme-count is the term that scales with draft
    /// size, and it used to run ~5× per keystroke at the 4000-char cap.
    @State private var trimmedCount: Int = 0

    private var isOverLimit: Bool { trimmedCount > charLimit }
    private var canSend: Bool { trimmedCount > 0 && !isOverLimit }

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            Button { onPickFiles() } label: {
                Image(systemName: "paperclip")
                    .font(.system(size: 17))
                    .foregroundColor(
                        isUploadingImages ? Color.secondary.opacity(0.35) : .secondary
                    )
            }
            .buttonStyle(.plain)
            .disabled(isUploadingImages)
            .help("Attach files — images, PDF, DOC/DOCX, TXT, MD, CSV, JSON")

            TextField(placeholder, text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundColor(appState.themeText)
                .lineLimit(1...6)
                .padding(.vertical, 8)
                .onChange(of: text) { _, newValue in
                    // Hard cap: trim past the limit so paste-bombs can't bypass
                    // send-disable. The reassignment re-enters this handler,
                    // which is where trimmedCount then settles.
                    if newValue.count > charLimit {
                        text = String(newValue.prefix(charLimit))
                        return
                    }
                    trimmedCount = newValue
                        .trimmingCharacters(in: .whitespacesAndNewlines).count
                }
                .onChange(of: seedNonce) { applySeed() }
                .onKeyPress(keys: [.return], phases: .down) { press in
                    // Shift+Return must fall through to the field so the break
                    // lands at the caret. Handling it here (and appending "\n"
                    // manually) always put the newline at the END of the draft.
                    guard !press.modifiers.contains(.shift) else { return .ignored }
                    submit()
                    return .handled
                }

            if trimmedCount > charLimit - 500 {
                Text("\(trimmedCount)/\(charLimit)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(isOverLimit ? .red : .secondary)
                    .help("Messages are capped at \(charLimit) characters")
            }

            Button { submit() } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundColor(
                        canSend ? appState.themeAccent : appState.themeTextSecondary
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canSend || isStreaming)
        }
    }

    /// Send is allowed with no text when attachments are pending — the parent
    /// owns that rule, so an empty draft is still handed up and `send(_:)`
    /// decides.
    private func submit() {
        guard !isStreaming, !isOverLimit else { return }
        onSend(text)
    }

    private func applySeed() {
        text = seed
        trimmedCount = seed.trimmingCharacters(in: .whitespacesAndNewlines).count
    }
}
