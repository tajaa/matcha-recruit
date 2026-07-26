import SwiftUI

/// Natural-language ticket bar. Owns its text in LOCAL @State so keystrokes
/// re-render only this bar, not the whole board (binding the text to a board-
/// level @State made every keystroke re-render all columns/cards → laggy).
/// Reports the prompt up via `onDraft` only on submit.
struct AIComposeBar: View {
    @Environment(AppState.self) private var appState
    var isDrafting: Bool
    var error: String?
    var onDraft: (String) -> Void

    @State private var text = ""

    private var trimmed: String { text.trimmingCharacters(in: .whitespacesAndNewlines) }

    private func submit() {
        guard !trimmed.isEmpty, !isDrafting else { return }
        onDraft(text)
        text = ""
    }

    var body: some View {
        VStack(spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                // Short placeholder — the example-laden version forced the row
                // wider than a narrow split pane (Draft button clipped off the
                // edge). The example moved to .help.
                TextField("Describe a task to draft…", text: $text)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .frame(maxWidth: .infinity)
                    .onSubmit { submit() }
                    .help("e.g. \"fix the 503 in console <error> and assign haley\"")
                if isDrafting {
                    ProgressView().controlSize(.small)
                } else {
                    Button(action: submit) {
                        Text("Draft")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10).padding(.vertical, 4)
                            .background(appState.themeAccent)
                            .cornerRadius(5)
                    }
                    .buttonStyle(.plain)
                    .disabled(trimmed.isEmpty)
                }
            }
            if let err = error {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9)).foregroundColor(.orange)
                    Text(err).font(.system(size: 10)).foregroundColor(.orange)
                    Spacer()
                }
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(appState.themeAccent.opacity(0.06))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(appState.themeAccent.opacity(0.25), lineWidth: 1)
        )
        .cornerRadius(6)
        .padding(.horizontal, 12)
        .padding(.bottom, 4)
    }
}
