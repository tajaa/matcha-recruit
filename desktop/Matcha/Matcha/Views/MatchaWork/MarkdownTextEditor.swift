import SwiftUI
import AppKit

/// NSTextView-backed editor that exposes the current selection and lets
/// callers wrap it or insert text at the caret — needed for the blog post
/// formatting toolbar (bold / italic / link / image / video).
///
/// Use the `controller` binding to drive edits from outside the view. The
/// controller is the only supported cross-view handle to NSTextView.
struct MarkdownTextEditor: NSViewRepresentable {
    @Binding var text: String
    @Binding var controller: MarkdownEditorController

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            return scrollView
        }
        textView.isRichText = false
        textView.isEditable = true
        textView.isSelectable = true
        textView.allowsUndo = true
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.textColor = .white
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.insertionPointColor = .white
        textView.delegate = context.coordinator
        textView.textContainerInset = NSSize(width: 12, height: 12)
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.isAutomaticSpellingCorrectionEnabled = false
        textView.string = text

        scrollView.drawsBackground = false
        scrollView.backgroundColor = .clear

        controller.textView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.string != text {
            let sel = textView.selectedRange()
            textView.string = text
            let clamped = NSRange(location: min(sel.location, text.utf16.count), length: 0)
            textView.setSelectedRange(clamped)
        }
        controller.textView = textView
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MarkdownTextEditor
        init(_ parent: MarkdownTextEditor) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            parent.text = tv.string
        }
    }
}

/// Handle the toolbar uses to mutate the active editor. Lives as @State on
/// the owning view so the toolbar buttons and the NSTextView share one
/// reference.
final class MarkdownEditorController {
    weak var textView: NSTextView?

    /// Wrap the current selection with `left` and `right`. If nothing is
    /// selected, insert `left + placeholder + right` and select the
    /// placeholder so the user can type over it.
    func wrapSelection(left: String, right: String, placeholder: String = "text") {
        guard let tv = textView else { return }
        let sel = tv.selectedRange()
        let ns = tv.string as NSString
        let selected = sel.length > 0 ? ns.substring(with: sel) : placeholder
        let replacement = left + selected + right
        let cursorLocation: Int
        if sel.length > 0 {
            cursorLocation = sel.location + replacement.utf16.count
        } else {
            cursorLocation = sel.location + left.utf16.count
        }
        tv.insertText(replacement, replacementRange: sel)
        let selectLen = sel.length > 0 ? 0 : (placeholder as NSString).length
        tv.setSelectedRange(NSRange(location: cursorLocation - (sel.length > 0 ? 0 : selectLen), length: selectLen))
    }

    /// Prefix every line that intersects the current selection with `prefix`.
    /// Used for list / quote / heading commands.
    func prefixLines(with prefix: String) {
        guard let tv = textView else { return }
        let ns = tv.string as NSString
        let sel = tv.selectedRange()
        let lineRange = ns.lineRange(for: sel)
        let block = ns.substring(with: lineRange)
        let lines = block.split(separator: "\n", omittingEmptySubsequences: false)
        let transformed = lines.map { line -> String in
            line.isEmpty ? String(line) : prefix + line
        }.joined(separator: "\n")
        tv.insertText(transformed, replacementRange: lineRange)
    }

    /// Drop `text` at the caret on a fresh line (leading newline if mid-line,
    /// trailing newline always). Used for image / video embeds so they render
    /// as block elements.
    func insertBlock(_ text: String) {
        guard let tv = textView else { return }
        let ns = tv.string as NSString
        let sel = tv.selectedRange()
        let needsLeadingNewline: Bool
        if sel.location == 0 {
            needsLeadingNewline = false
        } else {
            let prev = ns.substring(with: NSRange(location: sel.location - 1, length: 1))
            needsLeadingNewline = prev != "\n"
        }
        let block = (needsLeadingNewline ? "\n" : "") + text + "\n"
        tv.insertText(block, replacementRange: sel)
    }
}
