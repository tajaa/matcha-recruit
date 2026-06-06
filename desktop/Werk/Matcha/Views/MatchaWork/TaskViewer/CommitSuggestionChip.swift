import SwiftUI

/// A Gemini proposal that a local git commit completed a checklist subtask.
/// Rendered just beneath its SubtaskRow; Accept ticks the box (server flips
/// is_done, history-logged), Dismiss clears the chip. Never auto-flips.
struct CommitSuggestionChip: View {
    let suggestion: MWCommitSuggestion
    let onAccept: () -> Void
    let onDismiss: () -> Void

    @State private var busy = false

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "sparkles")
                .font(.system(size: 9))
                .foregroundColor(.mwInkStrong)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    if let sha = suggestion.commitShortSha, !sha.isEmpty {
                        Text(sha)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.mwInkStrong)
                    }
                    Text("may have completed this")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
                if let r = suggestion.reasoning, !r.isEmpty {
                    Text(r)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary.opacity(0.85))
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 4)
            if busy {
                ProgressView().controlSize(.small)
            } else {
                Button {
                    busy = true
                    onAccept()
                } label: {
                    Text("Accept")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.mwInkStrong)
                }
                .buttonStyle(.plain)
                Button {
                    busy = true
                    onDismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Dismiss suggestion")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.mwInkStrong.opacity(0.08))
        .overlay(
            RoundedRectangle(cornerRadius: 5)
                .stroke(Color.mwInkStrong.opacity(0.25), lineWidth: 1)
        )
        .cornerRadius(5)
    }
}
