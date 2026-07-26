import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// SwiftUI wrapper around NSTextView. Surfaces the underlying text via a
/// binding, registers itself with a `JournalEditorController` so the toolbar
/// can mutate selection, and intercepts file drops to upload images and
/// inline their URLs.
///
/// What used to live in this file and now sits beside it:
///   • JournalEditorController.swift — the toolbar/shortcut command surface
///   • MarkdownListEditing.swift     — Return / Tab list continuation + outlining
///   • SlashMenuPanel.swift          — the "/" menu model, list, and NSPanel
///   • MarkdownStyler.swift          — the live attribute pass
struct RichJournalEditor: NSViewRepresentable {
    @Binding var text: String
    @ObservedObject var controller: JournalEditorController
    /// Display-only attributes (font family / size / line spacing).
    let fontFamily: String
    let fontSize: CGFloat
    let lineSpacing: CGFloat
    /// Optional minimum height; the enclosing layout still bounds max height.
    var minHeight: CGFloat = 80
    /// Blocks offered by the "/" slash menu. Empty = no slash menu.
    var slashBlocks: [SlashBlock] = []
    /// Body text color — theme-derived so the editor is legible on light themes
    /// (the old hardcoded white was invisible on platinum/light).
    var textColor: NSColor = .labelColor

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true

        guard let tv = scroll.documentView as? NSTextView else { return scroll }
        tv.delegate = context.coordinator
        // Rich text ON so the live-markdown styler's per-range attributes
        // (bold/headings/etc.) persist. Storage stays plain markdown — the
        // binding reads `tv.string`, and reload re-styles from scratch.
        tv.isRichText = true
        tv.importsGraphics = false
        tv.allowsUndo = true
        tv.isAutomaticQuoteSubstitutionEnabled = false
        tv.isAutomaticDashSubstitutionEnabled = false
        tv.isAutomaticTextReplacementEnabled = false
        tv.isAutomaticSpellingCorrectionEnabled = false
        tv.textContainerInset = NSSize(width: 6, height: 6)
        tv.backgroundColor = .clear
        tv.drawsBackground = false
        tv.font = font()
        tv.string = text
        tv.textColor = textColor
        tv.insertionPointColor = textColor
        tv.typingAttributes = typingAttributes()
        tv.registerForDraggedTypes([.fileURL, .tiff, .png])
        context.coordinator.bind(tv: tv)
        controller.textView = tv
        applyMarkdownStyling(to: tv)
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let tv = scroll.documentView as? NSTextView else { return }
        if tv.string != text {
            let sel = tv.selectedRange()
            tv.string = text
            // Clamp the saved selection to the new length.
            let len = (tv.string as NSString).length
            let safe = NSRange(location: min(sel.location, len), length: min(sel.length, max(0, len - sel.location)))
            tv.setSelectedRange(safe)
        }
        tv.insertionPointColor = textColor
        tv.typingAttributes = typingAttributes()
        applyMarkdownStyling(to: tv)
        tv.invalidateIntrinsicContentSize()
    }

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    /// Re-render the markdown source in place: bold/italic/headings/lists/code/
    /// links are styled live while the stored text stays plain markdown. Cheap
    /// enough to run on every keystroke for note-sized documents.
    func applyMarkdownStyling(to tv: NSTextView) {
        guard let storage = tv.textStorage else { return }
        MarkdownStyler.apply(
            to: storage, fullText: tv.string as NSString,
            baseFont: font(), textColor: textColor, lineSpacing: lineSpacing,
        )
        tv.typingAttributes = typingAttributes()
    }

    // MARK: - Attribute helpers

    private func font() -> NSFont {
        switch fontFamily {
        case "serif":      return NSFont(name: "Georgia", size: fontSize) ?? .systemFont(ofSize: fontSize)
        case "monospaced": return .monospacedSystemFont(ofSize: fontSize, weight: .regular)
        default:           return .systemFont(ofSize: fontSize)
        }
    }

    private func typingAttributes() -> [NSAttributedString.Key: Any] {
        let para = NSMutableParagraphStyle()
        para.lineSpacing = lineSpacing
        return [
            .font: font(),
            .foregroundColor: textColor,
            .paragraphStyle: para,
        ]
    }
}

// MARK: - Coordinator

extension RichJournalEditor {
    /// NSTextView delegate. Owns only the wiring now: push text into the
    /// binding, route Return/Tab to `MarkdownListEditing`, drive the slash
    /// panel, and run the drag-drop upload pipeline.
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: RichJournalEditor
        /// Map of placeholder tokens currently in the text so the upload
        /// callback can swap them out when complete.
        private var pendingPlaceholders: Set<String> = []
        /// The floating "/" command menu (panel + live query range).
        private let slash = SlashMenuPanel()

        init(parent: RichJournalEditor) {
            self.parent = parent
            super.init()
            slash.onPick = { [weak self] block in self?.commitSlash(block) }
        }

        func bind(tv: NSTextView) { /* hook for future delegate wiring */ }

        // MARK: - Text + selection

        // Text change → push into binding, then refresh the slash menu.
        func textDidChange(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            parent.text = tv.string
            // Live-render the markdown (also resets typing attributes so the
            // caret keeps writing plain text, not inheriting a styled run).
            parent.applyMarkdownStyling(to: tv)
            updateSlashMenu(tv)
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard slash.isActive, let tv = notification.object as? NSTextView else { return }
            updateSlashMenu(tv)   // caret moved out of the "/query" → dismiss
        }

        // Editor lost first responder (clicked away, switched view) → don't leave
        // a detached slash panel floating.
        func textDidEndEditing(_ notification: Notification) {
            slash.dismiss()
        }

        // Keyboard shortcuts: when the slash menu is open, the arrow keys /
        // return / tab / escape drive it instead of the text view. Otherwise
        // Return auto-continues markdown lists (Apple Notes style).
        func textView(_ tv: NSTextView, doCommandBy selector: Selector) -> Bool {
            if slash.isActive {
                switch selector {
                case #selector(NSResponder.moveDown(_:)):    slash.moveSelection(1);  return true
                case #selector(NSResponder.moveUp(_:)):      slash.moveSelection(-1); return true
                case #selector(NSResponder.insertNewline(_:)),
                     #selector(NSResponder.insertTab(_:)):   commitSlashSelection();  return true
                case #selector(NSResponder.cancelOperation(_:)): slash.dismiss();     return true
                default: return false
                }
            }
            if selector == #selector(NSResponder.insertNewline(_:)) {
                return apply(MarkdownListEditing.handleReturn(tv), to: tv)
            }
            if selector == #selector(NSResponder.insertTab(_:)) {
                return apply(MarkdownListEditing.handleIndent(tv, demote: true), to: tv)
            }
            if selector == #selector(NSResponder.insertBacktab(_:)) {
                return apply(MarkdownListEditing.handleIndent(tv, demote: false), to: tv)
            }
            return false
        }

        /// Sync the binding + re-style when a list edit actually changed text.
        /// Returns whether the key press was consumed.
        private func apply(_ outcome: MarkdownListEditing.Outcome, to tv: NSTextView) -> Bool {
            if case .edited = outcome {
                parent.text = tv.string
                parent.applyMarkdownStyling(to: tv)
            }
            if case .notHandled = outcome { return false }
            return true
        }

        // MARK: - Slash menu driving

        /// Recompute the live "/query" before the caret and show/refresh the
        /// floating menu, or dismiss when there's no active trigger.
        private func updateSlashMenu(_ tv: NSTextView) {
            guard !parent.slashBlocks.isEmpty else { slash.dismiss(); return }
            let sel = tv.selectedRange()
            guard sel.length == 0 else { slash.dismiss(); return }
            let ns = tv.string as NSString
            let caret = sel.location
            var slashIdx = -1
            var k = caret
            while k > 0 {
                let ch = ns.substring(with: NSRange(location: k - 1, length: 1))
                if ch == "/" { slashIdx = k - 1; break }
                if ch == " " || ch == "\n" || ch == "\t" { break }
                k -= 1
                if caret - k > 24 { break }   // queries don't run this long
            }
            guard slashIdx >= 0 else { slash.dismiss(); return }
            let boundaryOK: Bool = slashIdx == 0 || {
                let p = ns.substring(with: NSRange(location: slashIdx - 1, length: 1))
                return p == " " || p == "\n" || p == "\t"
            }()
            guard boundaryOK else { slash.dismiss(); return }
            let query = ns.substring(with: NSRange(location: slashIdx + 1, length: caret - slashIdx - 1))
            slash.show(blocks: parent.slashBlocks, query: query,
                       range: NSRange(location: slashIdx, length: caret - slashIdx), in: tv)
        }

        private func commitSlashSelection() {
            guard let block = slash.selectedBlock else { return }
            commitSlash(block)
        }

        private func commitSlash(_ block: SlashBlock) {
            // Always invoked on the main thread (key handling or a SwiftUI tap);
            // assert it so we can touch the @MainActor controller.
            MainActor.assumeIsolated {
                guard let tv = parent.controller.textView else { slash.dismiss(); return }
                let ns = tv.string as NSString
                let r = slash.range
                guard r.location >= 0, r.location + r.length <= ns.length else { slash.dismiss(); return }
                // Strip the "/query" first, then run the block's insert at that spot.
                if tv.shouldChangeText(in: r, replacementString: "") {
                    tv.textStorage?.replaceCharacters(in: r, with: "")
                    tv.didChangeText()
                }
                tv.setSelectedRange(NSRange(location: r.location, length: 0))
                slash.dismiss()
                switch block.insert {
                case .linePrefix(let p): parent.controller.togglePrefix(p)
                case .snippet(let s):    parent.controller.insertSnippet(s)
                case .image:             parent.controller.pickImage()
                case .link:              parent.controller.wrapLink()
                }
                parent.text = tv.string
            }
        }

        // MARK: - Context menu

        // Right-click menu: add "Create to-do from selection" when text is
        // selected. Routes the selection to the host via the controller closure.
        func textView(_ textView: NSTextView, menu: NSMenu, for event: NSEvent, at charIndex: Int) -> NSMenu? {
            let sel = textView.selectedRange()
            guard sel.length > 0 else { return menu }
            let text = (textView.string as NSString).substring(with: sel)
            let todo = NSMenuItem(title: "Create to-do from selection",
                                  action: #selector(createTodoFromSelection(_:)), keyEquivalent: "")
            todo.target = self; todo.representedObject = text
            let calendar = NSMenuItem(title: "Add to calendar (today)",
                                      action: #selector(addToCalendarFromSelection(_:)), keyEquivalent: "")
            calendar.target = self; calendar.representedObject = text
            menu.insertItem(.separator(), at: 0)
            menu.insertItem(calendar, at: 0)
            menu.insertItem(todo, at: 0)
            return menu
        }

        @objc private func createTodoFromSelection(_ sender: NSMenuItem) {
            guard let text = sender.representedObject as? String else { return }
            MainActor.assumeIsolated { parent.controller.onCreateTodo?(text) }
        }

        @objc private func addToCalendarFromSelection(_ sender: NSMenuItem) {
            guard let text = sender.representedObject as? String else { return }
            MainActor.assumeIsolated { parent.controller.onAddToCalendar?(text) }
        }

        // MARK: - Drag-drop images

        // Drag-drop image handling — NSTextView default would embed an
        // attachment; we intercept and upload instead.
        func textView(
            _ tv: NSTextView,
            shouldChangeTextIn affectedCharRange: NSRange,
            replacementString: String?,
        ) -> Bool { true }

        @MainActor
        func handleDrop(files: [URL], at insertionPoint: Int, in tv: NSTextView) {
            for url in files where JournalEditorController.isImage(url: url) {
                let placeholder = "![Uploading…](pending-\(UUID().uuidString.prefix(6)))"
                pendingPlaceholders.insert(placeholder)
                // Insert placeholder synchronously so the user sees feedback.
                let ns = tv.string as NSString
                let safePoint = max(0, min(insertionPoint, ns.length))
                let range = NSRange(location: safePoint, length: 0)
                if tv.shouldChangeText(in: range, replacementString: placeholder) {
                    tv.textStorage?.replaceCharacters(in: range, with: placeholder)
                    tv.didChangeText()
                    parent.text = tv.string
                }
                Task { [weak self] in
                    guard let self = self else { return }
                    guard let data = try? Data(contentsOf: url) else {
                        self.parent.controller.replacePlaceholder(placeholder, with: "![upload failed]()")
                        self.parent.text = tv.string
                        self.pendingPlaceholders.remove(placeholder)
                        return
                    }
                    let mime = JournalEditorController.imageMimeType(for: url)
                    let resolved = await self.parent.controller.onUploadImage?(data, url.lastPathComponent, mime)
                    if let resolved {
                        self.parent.controller.replacePlaceholder(placeholder, with: "![](\(resolved))")
                    } else {
                        self.parent.controller.replacePlaceholder(placeholder, with: "![upload failed]()")
                    }
                    self.parent.text = tv.string
                    self.pendingPlaceholders.remove(placeholder)
                }
            }
        }
    }
}
