import SwiftUI
import AppKit

/// NSTextView-backed editor that exposes the current selection and lets
/// callers wrap it or insert text at the caret — needed for the blog post
/// formatting toolbar (bold / italic / link / image / video).
///
/// Use the `controller` binding to drive edits from outside the view. The
/// controller is the only supported cross-view handle to NSTextView.
/// A remote collaborator's caret/selection inside the document, rendered as a
/// colored bar (+ name label) at their text position. UTF-16 offsets to match
/// NSTextView's `selectedRange`.
struct RemoteCaretMark: Identifiable, Equatable {
    let id: String          // userId
    let color: Color
    let name: String
    let anchor: Int
    let head: Int
    var range: NSRange {
        let lo = min(anchor, head), hi = max(anchor, head)
        return NSRange(location: max(0, lo), length: max(0, hi - lo))
    }
}

/// A commented text range, drawn as a yellow highlight and clickable to open
/// its thread.
struct CommentHighlightMark: Identifiable, Equatable {
    let id: String          // commentId (the thread root)
    let anchor: Int
    let head: Int
    var range: NSRange {
        let lo = min(anchor, head), hi = max(anchor, head)
        return NSRange(location: max(0, lo), length: max(0, hi - lo))
    }
}

struct MarkdownTextEditor: NSViewRepresentable {
    @Binding var text: String
    @Binding var controller: MarkdownEditorController
    /// Fires whenever the user moves the caret or changes the selection.
    /// `anchor` and `head` are character offsets (UTF-16 to match
    /// NSTextView's selectedRange). Used by collab presence to broadcast
    /// remote-caret position; nil for editors that don't broadcast.
    var onSelectionChange: ((Int, Int) -> Void)? = nil
    /// When false the text view is read-only (watcher mode) — still selectable
    /// so the reader can copy, but not editable.
    var isEditable: Bool = true
    /// Remote collaborators' carets to draw in-text (e.g. the lock holder's
    /// caret, shown to watchers). Empty for the active editor.
    var remoteCarets: [RemoteCaretMark] = []
    /// Commented text ranges to highlight (yellow), clickable to open the
    /// thread. Resolved comments are filtered out by the caller.
    var commentHighlights: [CommentHighlightMark] = []
    /// A commented highlight was clicked — (commentId, rect in editor-local
    /// coordinates) so the caller can anchor a thread popover.
    var onCommentTap: ((String, CGRect) -> Void)? = nil
    /// The selection changed: rect (editor-local, nil when empty) + char range.
    /// Drives the "add comment" affordance on a fresh selection.
    var onSelectionRectChange: ((CGRect?, Int, Int) -> Void)? = nil

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            return scrollView
        }
        textView.isRichText = false
        textView.isEditable = isEditable
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

        // Comment-highlight overlay FIRST (lower in z-order) so it can catch
        // clicks on highlights; the caret overlay above it is click-through.
        let commentOverlay = CommentHighlightOverlay(frame: textView.bounds)
        commentOverlay.textView = textView
        commentOverlay.autoresizingMask = [.width, .height]
        commentOverlay.marks = commentHighlights
        commentOverlay.onTap = onCommentTap
        textView.addSubview(commentOverlay)
        context.coordinator.commentOverlay = commentOverlay

        // Transparent overlay (child of the text view, so it scrolls + resizes
        // with the content) that draws remote collaborators' carets in-text.
        let overlay = RemoteCaretOverlay(frame: textView.bounds)
        overlay.textView = textView
        overlay.autoresizingMask = [.width, .height]
        overlay.marks = remoteCarets
        textView.addSubview(overlay)
        context.coordinator.overlay = overlay

        scrollView.drawsBackground = false
        scrollView.backgroundColor = .clear

        controller.textView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.isEditable != isEditable { textView.isEditable = isEditable }
        if textView.string != text {
            let sel = textView.selectedRange()
            textView.string = text
            let clamped = NSRange(location: min(sel.location, text.utf16.count), length: 0)
            textView.setSelectedRange(clamped)
        }
        if let overlay = context.coordinator.overlay {
            overlay.frame = textView.bounds
            overlay.marks = remoteCarets
        }
        if let commentOverlay = context.coordinator.commentOverlay {
            commentOverlay.frame = textView.bounds
            commentOverlay.marks = commentHighlights
            commentOverlay.onTap = onCommentTap
        }
        controller.textView = textView
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MarkdownTextEditor
        weak var overlay: RemoteCaretOverlay?
        weak var commentOverlay: CommentHighlightOverlay?
        init(_ parent: MarkdownTextEditor) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            parent.text = tv.string
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            let sel = tv.selectedRange()
            // anchor + head distinguish the start vs end of the selection so
            // the receiver can render a directional selection bar. NSTextView
            // doesn't expose direction; we treat anchor as start and head as
            // start+length — close enough for rendering, matches web behavior.
            parent.onSelectionChange?(sel.location, sel.location + sel.length)

            // Report the selection rect (for the "add comment" affordance) in
            // the enclosing scroll view's coords, so a SwiftUI overlay can pin
            // a bubble to it.
            guard let report = parent.onSelectionRectChange else { return }
            if sel.length > 0, let lm = tv.layoutManager, let tc = tv.textContainer {
                let gr = lm.glyphRange(forCharacterRange: sel, actualCharacterRange: nil)
                var rect = lm.boundingRect(forGlyphRange: gr, in: tc)
                    .offsetBy(dx: tv.textContainerOrigin.x, dy: tv.textContainerOrigin.y)
                if let sv = tv.enclosingScrollView {
                    rect = tv.convert(rect, to: sv)
                }
                report(rect, sel.location, sel.location + sel.length)
            } else {
                report(nil, sel.location, sel.location)
            }
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

/// Transparent overlay drawn on top of an `NSTextView` that renders remote
/// collaborators' carets/selections at their text position. Lives as a child
/// of the text view so it shares the (flipped) text coordinate space and
/// scrolls/resizes with the content. Hit-transparent so it never steals
/// clicks from the editor underneath.
final class RemoteCaretOverlay: NSView {
    weak var textView: NSTextView?
    var marks: [RemoteCaretMark] = [] { didSet { needsDisplay = true } }

    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard !marks.isEmpty,
              let tv = textView,
              let lm = tv.layoutManager,
              let tc = tv.textContainer else { return }
        let origin = tv.textContainerOrigin
        let nsLen = (tv.string as NSString).length

        for mark in marks {
            let r = mark.range
            // Clamp to current text length — the caret stream can briefly lead
            // the content stream, so offsets may overshoot.
            let loc = min(r.location, nsLen)
            let len = min(r.length, max(0, nsLen - loc))
            let charRange = NSRange(location: loc, length: len)
            let glyphRange = lm.glyphRange(forCharacterRange: charRange, actualCharacterRange: nil)

            var rect = lm.boundingRect(forGlyphRange: glyphRange, in: tc)
            if rect.height <= 0 {
                // End-of-text / empty line: fall back to the extra line fragment.
                let extra = lm.extraLineFragmentRect
                rect = extra.height > 0 ? extra : rect
            }
            rect = rect.offsetBy(dx: origin.x, dy: origin.y)
            let color = NSColor(mark.color)

            if len == 0 {
                // Caret: a thin vertical bar.
                let bar = NSRect(x: rect.minX, y: rect.minY, width: 2, height: max(rect.height, 14))
                color.setFill()
                bar.fill()
                drawLabel(mark.name, color: color, atTopOf: bar)
            } else {
                // Selection: translucent highlight + label at its start.
                color.withAlphaComponent(0.22).setFill()
                rect.fill()
                let caret = NSRect(x: rect.minX, y: rect.minY, width: 2, height: max(rect.height, 14))
                drawLabel(mark.name, color: color, atTopOf: caret)
            }
        }
    }

    private func drawLabel(_ name: String, color: NSColor, atTopOf bar: NSRect) {
        guard !name.isEmpty else { return }
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 9, weight: .medium),
            .foregroundColor: NSColor.white,
        ]
        let label = name as NSString
        let size = label.size(withAttributes: attrs)
        let pad: CGFloat = 3
        let bg = NSRect(
            x: bar.minX,
            y: max(0, bar.minY - size.height - 3),
            width: size.width + pad * 2,
            height: size.height + 2
        )
        color.setFill()
        NSBezierPath(roundedRect: bg, xRadius: 3, yRadius: 3).fill()
        label.draw(at: NSPoint(x: bg.minX + pad, y: bg.minY + 1), withAttributes: attrs)
    }
}

/// Draws yellow highlights under commented ranges and makes them clickable to
/// open the comment thread. Click-through everywhere EXCEPT on a highlight, so
/// it never steals selection/editing from the text view underneath.
final class CommentHighlightOverlay: NSView {
    weak var textView: NSTextView?
    var onTap: ((String, CGRect) -> Void)?
    var marks: [CommentHighlightMark] = [] { didSet { needsDisplay = true } }

    /// Per-line hit rects (overlay coords) mapped to their comment id, rebuilt
    /// each draw so hit-testing matches what's painted.
    private var hitRects: [(rect: NSRect, id: String)] = []

    override var isFlipped: Bool { true }

    override func hitTest(_ point: NSPoint) -> NSView? {
        let local = convert(point, from: superview)
        return hitRects.contains(where: { $0.rect.contains(local) }) ? self : nil
    }

    override func mouseDown(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if let hit = hitRects.first(where: { $0.rect.contains(p) }) {
            onTap?(hit.id, hit.rect)
        }
    }

    private func enclosingRects(for range: NSRange, lm: NSLayoutManager, tc: NSTextContainer, origin: NSPoint, nsLen: Int) -> [NSRect] {
        let loc = min(range.location, nsLen)
        let len = min(range.length, max(0, nsLen - loc))
        guard len > 0 else { return [] }
        let glyphRange = lm.glyphRange(forCharacterRange: NSRange(location: loc, length: len), actualCharacterRange: nil)
        var rects: [NSRect] = []
        lm.enumerateEnclosingRects(
            forGlyphRange: glyphRange,
            withinSelectedGlyphRange: NSRange(location: NSNotFound, length: 0),
            in: tc
        ) { rect, _ in
            rects.append(rect.offsetBy(dx: origin.x, dy: origin.y))
        }
        return rects
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        hitRects = []
        guard !marks.isEmpty,
              let tv = textView,
              let lm = tv.layoutManager,
              let tc = tv.textContainer else { return }
        let origin = tv.textContainerOrigin
        let nsLen = (tv.string as NSString).length
        let fill = NSColor.systemYellow.withAlphaComponent(0.28)
        let underline = NSColor.systemYellow.withAlphaComponent(0.9)

        for mark in marks {
            for r in enclosingRects(for: mark.range, lm: lm, tc: tc, origin: origin, nsLen: nsLen) {
                fill.setFill()
                NSBezierPath(roundedRect: r.insetBy(dx: -1, dy: 0), xRadius: 2, yRadius: 2).fill()
                // Bottom rule so a highlight reads as "commented" even on a
                // pale background.
                underline.setFill()
                NSRect(x: r.minX, y: r.maxY - 1.5, width: r.width, height: 1.5).fill()
                hitRects.append((r, mark.id))
            }
        }
    }
}
