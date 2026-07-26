import SwiftUI

// MARK: - Markdown formatting toolbar
//
// Split out of SectionEditorView.swift.

extension SectionEditorView {

    @ViewBuilder
    var formattingToolbar: some View {
        HStack(spacing: 3) {
            toolbarButton("B", bold: true, help: "Bold") {
                controller.wrapSelection(left: "**", right: "**", placeholder: "bold")
            }
            toolbarButton("I", italic: true, help: "Italic") {
                controller.wrapSelection(left: "*", right: "*", placeholder: "italic")
            }
            toolbarButton("H1", help: "Heading 1") {
                controller.prefixLines(with: "# ")
            }
            toolbarButton("H2", help: "Heading 2") {
                controller.prefixLines(with: "## ")
            }
            toolbarIcon("list.bullet", help: "Bulleted list") {
                controller.prefixLines(with: "- ")
            }
            toolbarIcon("list.number", help: "Numbered list") {
                controller.prefixLines(with: "1. ")
            }
            toolbarIcon("text.quote", help: "Quote") {
                controller.prefixLines(with: "> ")
            }
            toolbarIcon("chevron.left.forwardslash.chevron.right", help: "Inline code") {
                controller.wrapSelection(left: "`", right: "`", placeholder: "code")
            }
            toolbarIcon("link", help: "Link") {
                controller.wrapSelection(left: "[", right: "](https://)", placeholder: "text")
            }
            Divider().frame(height: 14).padding(.horizontal, 2)
            lineSpacingButton("1×", "1.0", help: "Single line spacing")
            lineSpacingButton("1.5", "1.5", help: "1.5 line spacing")
            lineSpacingButton("2×", "2.0", help: "Double line spacing")
            Divider().frame(height: 14).padding(.horizontal, 2)
            toolbarIcon("photo", help: projectId == nil ? "Image (no project)" : "Insert image (max 50 MB)") {
                pickMedia(kind: .image)
            }
            .disabled(projectId == nil)
            toolbarIcon("video", help: projectId == nil ? "Video (no project)" : "Insert video (max 50 MB)") {
                pickMedia(kind: .video)
            }
            .disabled(projectId == nil)
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 6)
        .background(Color.zinc800.opacity(0.35))
        .overlay(
            Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.08)),
            alignment: .bottom
        )
    }

    /// The three spacing buttons differ only by the number they write into the
    /// wrapping div — they were three copies of the same five lines.
    private func lineSpacingButton(_ label: String, _ value: String, help: String) -> some View {
        toolbarButton(label, help: help) {
            controller.wrapSelection(
                left: "<div style=\"line-height:\(value)\">\n",
                right: "\n</div>",
                placeholder: "text"
            )
        }
    }

    private func toolbarButton(_ label: String, bold: Bool = false, italic: Bool = false, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: bold ? .bold : .medium, design: .default))
                .italic(italic)
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }

    private func toolbarIcon(_ systemName: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 11))
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }
}
