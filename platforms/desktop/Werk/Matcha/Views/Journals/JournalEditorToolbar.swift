import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Strip of icon buttons that drive a `JournalEditorController`. Sits above
/// the editor view; toolbar actions and Cmd-shortcuts both route through
/// the controller so they share state and behavior.
struct JournalEditorToolbar: View {
    @ObservedObject var controller: JournalEditorController

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 2) {
                btn("bold", help: "Bold (⌘B)") { controller.toggleWrap(prefix: "**") }
                    .keyboardShortcut("b", modifiers: .command)
                btn("italic", help: "Italic (⌘I)") { controller.toggleWrap(prefix: "*") }
                    .keyboardShortcut("i", modifiers: .command)
                btn("strikethrough", help: "Strikethrough (⇧⌘S)") { controller.toggleWrap(prefix: "~~") }
                    .keyboardShortcut("s", modifiers: [.command, .shift])
                btn("highlighter", help: "Highlight (⇧⌘H)") { controller.toggleWrap(prefix: "==") }
                    .keyboardShortcut("h", modifiers: [.command, .shift])
                divider
                btnText("H1", help: "Heading 1 (⌘1)") { controller.togglePrefix("# ") }
                    .keyboardShortcut("1", modifiers: .command)
                btnText("H2", help: "Heading 2 (⌘2)") { controller.togglePrefix("## ") }
                    .keyboardShortcut("2", modifiers: .command)
                btnText("H3", help: "Heading 3 (⌘3)") { controller.togglePrefix("### ") }
                    .keyboardShortcut("3", modifiers: .command)
                divider
                btn("list.bullet", help: "Bullet list (⇧⌘8)") { controller.togglePrefix("- ") }
                    .keyboardShortcut("8", modifiers: [.command, .shift])
                btn("list.number", help: "Numbered list (⇧⌘9)") { controller.togglePrefix("1. ") }
                    .keyboardShortcut("9", modifiers: [.command, .shift])
                btn("checklist", help: "To-do (⇧⌘T)") { controller.togglePrefix("- [ ] ") }
                    .keyboardShortcut("t", modifiers: [.command, .shift])
                btn("text.quote", help: "Quote") { controller.togglePrefix("> ") }
                divider
                btn("curlybraces", help: "Inline code") { controller.toggleWrap(prefix: "`") }
                btn("chevron.left.forwardslash.chevron.right", help: "Code block") { controller.insertCodeBlock() }
                btn("function", help: "Math (LaTeX)") { controller.insertSnippet("\n$$\n\n$$\n") }
                btn("point.3.connected.trianglepath.dotted", help: "Diagram (Mermaid)") {
                    controller.insertSnippet("\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n")
                }
                btn("link", help: "Link (⌘K)") { controller.wrapLink() }
                    .keyboardShortcut("k", modifiers: .command)
                btn("photo", help: "Insert image") { controller.pickImage() }
                btn("minus", help: "Divider") { controller.insertDivider() }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
        }
        .background(Color.zinc900.opacity(0.6))
        .cornerRadius(4)
    }

    private var divider: some View {
        Rectangle().fill(Color.white.opacity(0.08))
            .frame(width: 1, height: 14)
            .padding(.horizontal, 3)
    }

    private func btn(_ symbol: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.white.opacity(0.75))
                .frame(width: 22, height: 20)
                .background(Color.white.opacity(0.001))
        }
        .buttonStyle(.plain)
        .help(help)
        .onHover { hovering in
            if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
    }

    private func btnText(_ label: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.white.opacity(0.75))
                .frame(width: 22, height: 20)
        }
        .buttonStyle(.plain)
        .help(help)
    }

}
