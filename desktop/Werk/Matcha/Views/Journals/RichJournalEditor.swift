import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Controller surface shared between the editor view and its toolbar so the
/// same selection-mutating routines back both keyboard shortcuts and the
/// toolbar icon buttons. The editor view registers its NSTextView with the
/// controller on `makeNSView`; toolbar buttons call into the controller and
/// the controller drives the text view directly.
@MainActor
final class JournalEditorController: ObservableObject {
    weak var textView: NSTextView?
    /// Closure invoked when an image is dropped or chosen via the toolbar.
    /// Implementation should upload the bytes and return a public URL
    /// (or nil on failure — the placeholder token gets cleared).
    var onUploadImage: ((Data, String, String) async -> String?)?

    // MARK: - Inline wraps

    func toggleWrap(prefix: String, suffix: String? = nil) {
        guard let tv = textView else { return }
        let suf = suffix ?? prefix
        let nsText = tv.string as NSString
        let sel = tv.selectedRange()
        let selText = nsText.substring(with: sel)

        // If selection already wrapped, strip the markers; otherwise wrap.
        if selText.hasPrefix(prefix), selText.hasSuffix(suf), selText.count >= prefix.count + suf.count {
            let inner = (selText as NSString).substring(
                with: NSRange(location: prefix.count, length: selText.count - prefix.count - suf.count),
            )
            replace(range: sel, with: inner)
            tv.setSelectedRange(NSRange(location: sel.location, length: (inner as NSString).length))
            return
        }
        // Look outward: are markers already adjacent? Strip them.
        let outerStart = sel.location - prefix.count
        let outerEnd = sel.location + sel.length
        if outerStart >= 0, outerEnd + suf.count <= nsText.length {
            let leading = nsText.substring(with: NSRange(location: outerStart, length: prefix.count))
            let trailing = nsText.substring(with: NSRange(location: outerEnd, length: suf.count))
            if leading == prefix, trailing == suf {
                let total = NSRange(location: outerStart, length: prefix.count + sel.length + suf.count)
                replace(range: total, with: selText)
                tv.setSelectedRange(NSRange(location: outerStart, length: (selText as NSString).length))
                return
            }
        }
        let wrapped = "\(prefix)\(selText)\(suf)"
        replace(range: sel, with: wrapped)
        if selText.isEmpty {
            tv.setSelectedRange(NSRange(location: sel.location + prefix.count, length: 0))
        } else {
            tv.setSelectedRange(NSRange(location: sel.location, length: (wrapped as NSString).length))
        }
    }

    // MARK: - Line prefixes

    /// Prepend or toggle a prefix on every line touched by the current
    /// selection. Toggling: if the prefix is already present on the first
    /// touched line we strip it instead of stacking it again.
    func togglePrefix(_ prefix: String) {
        guard let tv = textView else { return }
        let ns = tv.string as NSString
        let sel = tv.selectedRange()
        let lineRange = ns.lineRange(for: sel)
        let block = ns.substring(with: lineRange)
        let lines = block.components(separatedBy: "\n")
        // Drop a trailing empty produced by a final newline in the block.
        let trimmedLines: [String]
        let hadTrailing = block.hasSuffix("\n")
        if hadTrailing, lines.last == "" { trimmedLines = Array(lines.dropLast()) } else { trimmedLines = lines }

        let allHave = trimmedLines.allSatisfy { $0.hasPrefix(prefix) }
        let mapped: [String]
        if allHave {
            mapped = trimmedLines.map { String($0.dropFirst(prefix.count)) }
        } else {
            mapped = trimmedLines.map { $0.isEmpty ? prefix : (($0.hasPrefix(prefix) ? $0 : prefix + $0)) }
        }
        var joined = mapped.joined(separator: "\n")
        if hadTrailing { joined += "\n" }
        replace(range: lineRange, with: joined)
        // Re-select the whole edited block so successive shortcuts keep
        // operating on the same content.
        tv.setSelectedRange(NSRange(location: lineRange.location, length: (joined as NSString).length))
    }

    // MARK: - Link / image / divider helpers

    func wrapLink() {
        guard let tv = textView else { return }
        let sel = tv.selectedRange()
        let ns = tv.string as NSString
        let selText = ns.substring(with: sel)
        let label = selText.isEmpty ? "text" : selText
        let inserted = "[\(label)](url)"
        replace(range: sel, with: inserted)
        // Position cursor inside `(url)` so the user can paste/type the URL.
        let cursor = sel.location + label.count + 3 // after "[label]("
        tv.setSelectedRange(NSRange(location: cursor, length: 3)) // selects "url"
    }

    func insertDivider() { insertBlock("\n---\n") }
    func insertCodeBlock() { insertBlock("\n```\ncode\n```\n") }

    /// Insert a string as its own block, ensuring a newline boundary before
    /// the cursor when needed.
    private func insertBlock(_ text: String) {
        guard let tv = textView else { return }
        replace(range: tv.selectedRange(), with: text)
    }

    /// Insert markdown image syntax with a real URL at the cursor.
    func insertImage(url: String, alt: String = "") {
        guard let tv = textView else { return }
        let token = "![\(alt)](\(url))"
        replace(range: tv.selectedRange(), with: token)
    }

    /// Insert a raw snippet (e.g. a divider or fenced code block) as its own
    /// block at the cursor. Shared by toolbar buttons and the "/" slash menu.
    func insertSnippet(_ text: String) { insertBlock(text) }

    /// Show a file picker, upload the chosen image, and inline its URL. Shared
    /// by the toolbar photo button and the "/image" slash command so both paths
    /// behave identically.
    func pickImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType.image]
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url,
              let data = try? Data(contentsOf: url) else { return }
        let mime = Self.imageMimeType(for: url)
        let alt = "Uploading-\(UUID().uuidString.prefix(8))"
        let placeholder = "![\(alt)](pending)"
        insertImage(url: "pending", alt: alt)
        Task { @MainActor in
            guard let resolved = await onUploadImage?(data, url.lastPathComponent, mime) else {
                replacePlaceholder(placeholder, with: "![upload failed]()")
                return
            }
            replacePlaceholder(placeholder, with: "![](\(resolved))")
        }
    }

    static func imageMimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "gif": return "image/gif"
        case "webp": return "image/webp"
        case "heic": return "image/heic"
        default: return "application/octet-stream"
        }
    }

    /// Replace the placeholder token with a real (or failure-marker) URL.
    /// Used by the drop pipeline: we drop a placeholder at the cursor while
    /// the upload runs, then swap it out when the URL resolves.
    func replacePlaceholder(_ placeholder: String, with replacement: String) {
        guard let tv = textView else { return }
        let ns = tv.string as NSString
        let range = ns.range(of: placeholder)
        guard range.location != NSNotFound else { return }
        replace(range: range, with: replacement)
        tv.setSelectedRange(NSRange(location: range.location + (replacement as NSString).length, length: 0))
    }

    // MARK: - Low-level edit

    private func replace(range: NSRange, with text: String) {
        guard let tv = textView else { return }
        guard tv.shouldChangeText(in: range, replacementString: text) else { return }
        tv.textStorage?.replaceCharacters(in: range, with: text)
        tv.didChangeText()
    }
}

/// SwiftUI wrapper around NSTextView. Surfaces the underlying text via a
/// binding, registers itself with a `JournalEditorController` so the toolbar
/// can mutate selection, and intercepts file drops to upload images and
/// inline their URLs.
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
        tv.isRichText = false
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
        tv.font = font()
        tv.textColor = textColor
        tv.insertionPointColor = textColor
        tv.typingAttributes = typingAttributes()
        tv.invalidateIntrinsicContentSize()
    }

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

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

    // MARK: - Coordinator

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: RichJournalEditor
        /// Map of placeholder tokens currently in the text so the upload
        /// callback can swap them out when complete.
        private var pendingPlaceholders: Set<String> = []
        init(parent: RichJournalEditor) { self.parent = parent }
        deinit { slashPanel?.orderOut(nil) }

        func bind(tv: NSTextView) { /* hook for future delegate wiring */ }

        // MARK: Slash menu state
        private var slashActive = false
        private var slashRange = NSRange(location: 0, length: 0)
        private var slashPanel: NSPanel?
        private var slashHost: NSHostingView<SlashMenuView>?
        private var slashModel: SlashMenuModel?

        // Text change → push into binding, then refresh the slash menu.
        func textDidChange(_ notification: Notification) {
            guard let tv = notification.object as? NSTextView else { return }
            // Re-apply typing attributes so newly typed text picks up
            // current font/spacing instead of inheriting from prior runs.
            tv.typingAttributes = parent.typingAttributes()
            parent.text = tv.string
            updateSlashMenu(tv)
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard slashActive, let tv = notification.object as? NSTextView else { return }
            updateSlashMenu(tv)   // caret moved out of the "/query" → dismiss
        }

        // Editor lost first responder (clicked away, switched view) → don't leave
        // a detached slash panel floating.
        func textDidEndEditing(_ notification: Notification) {
            dismissSlash()
        }

        // Keyboard shortcuts: when the slash menu is open, the arrow keys /
        // return / tab / escape drive it instead of the text view.
        func textView(_ tv: NSTextView, doCommandBy selector: Selector) -> Bool {
            guard slashActive else { return false }
            switch selector {
            case #selector(NSResponder.moveDown(_:)):    moveSlashSelection(1);  return true
            case #selector(NSResponder.moveUp(_:)):      moveSlashSelection(-1); return true
            case #selector(NSResponder.insertNewline(_:)),
                 #selector(NSResponder.insertTab(_:)):   commitSlashSelection(); return true
            case #selector(NSResponder.cancelOperation(_:)): dismissSlash();     return true
            default: return false
            }
        }

        // MARK: Slash menu driving

        /// Recompute the live "/query" before the caret and show/refresh the
        /// floating menu, or dismiss when there's no active trigger.
        private func updateSlashMenu(_ tv: NSTextView) {
            guard !parent.slashBlocks.isEmpty else { dismissSlash(); return }
            let sel = tv.selectedRange()
            guard sel.length == 0 else { dismissSlash(); return }
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
            guard slashIdx >= 0 else { dismissSlash(); return }
            let boundaryOK: Bool = slashIdx == 0 || {
                let p = ns.substring(with: NSRange(location: slashIdx - 1, length: 1))
                return p == " " || p == "\n" || p == "\t"
            }()
            guard boundaryOK else { dismissSlash(); return }
            let query = ns.substring(with: NSRange(location: slashIdx + 1, length: caret - slashIdx - 1))
            showSlash(tv: tv, query: query, range: NSRange(location: slashIdx, length: caret - slashIdx))
        }

        private func showSlash(tv: NSTextView, query: String, range: NSRange) {
            let q = query.lowercased()
            let filtered = q.isEmpty ? parent.slashBlocks : parent.slashBlocks.filter { b in
                b.title.lowercased().contains(q) || b.keywords.contains { $0.lowercased().contains(q) }
            }
            guard !filtered.isEmpty else { dismissSlash(); return }
            slashRange = range
            let model = ensureSlashMenu()
            model.blocks = filtered
            if model.selection >= filtered.count { model.selection = 0 }
            positionSlashPanel(tv: tv, at: range.location)
            slashPanel?.orderFront(nil)
            slashActive = true
        }

        private func ensureSlashMenu() -> SlashMenuModel {
            if let m = slashModel { return m }
            let m = SlashMenuModel()
            m.onPick = { [weak self] block in self?.commitSlash(block) }
            let host = NSHostingView(rootView: SlashMenuView(model: m))
            let panel = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: 248, height: 200),
                styleMask: [.nonactivatingPanel, .borderless],
                backing: .buffered, defer: true,
            )
            panel.isFloatingPanel = true
            panel.level = .popUpMenu
            panel.hasShadow = true
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.contentView = host
            slashModel = m
            slashHost = host
            slashPanel = panel
            return m
        }

        private func positionSlashPanel(tv: NSTextView, at charIndex: Int) {
            // firstRect returns the caret rect in SCREEN coordinates (y-up).
            let caretRect = tv.firstRect(
                forCharacterRange: NSRange(location: charIndex, length: 0), actualRange: nil,
            )
            let h = slashHost?.fittingSize.height ?? 200
            let gap: CGFloat = 4
            let originX = caretRect.minX
            let originY = caretRect.minY - gap - h   // drop the panel just below the caret
            slashPanel?.setFrame(NSRect(x: originX, y: originY, width: 248, height: max(h, 1)), display: true)
        }

        private func moveSlashSelection(_ delta: Int) {
            guard let m = slashModel, !m.blocks.isEmpty else { return }
            let n = m.blocks.count
            m.selection = ((m.selection + delta) % n + n) % n
        }

        private func commitSlashSelection() {
            guard let m = slashModel, m.selection < m.blocks.count else { return }
            commitSlash(m.blocks[m.selection])
        }

        private func commitSlash(_ block: SlashBlock) {
            // Always invoked on the main thread (key handling or a SwiftUI tap);
            // assert it so we can touch the @MainActor controller.
            MainActor.assumeIsolated {
                guard let tv = parent.controller.textView else { dismissSlash(); return }
                let ns = tv.string as NSString
                let r = slashRange
                guard r.location >= 0, r.location + r.length <= ns.length else { dismissSlash(); return }
                // Strip the "/query" first, then run the block's insert at that spot.
                if tv.shouldChangeText(in: r, replacementString: "") {
                    tv.textStorage?.replaceCharacters(in: r, with: "")
                    tv.didChangeText()
                }
                tv.setSelectedRange(NSRange(location: r.location, length: 0))
                dismissSlash()
                switch block.insert {
                case .linePrefix(let p): parent.controller.togglePrefix(p)
                case .snippet(let s):    parent.controller.insertSnippet(s)
                case .image:             parent.controller.pickImage()
                case .link:              parent.controller.wrapLink()
                }
                parent.text = tv.string
            }
        }

        private func dismissSlash() {
            guard slashActive || slashPanel != nil else { return }
            slashActive = false
            slashPanel?.orderOut(nil)
        }

        // Drag-drop image handling — NSTextView default would embed an
        // attachment; we intercept and upload instead.
        func textView(
            _ tv: NSTextView,
            shouldChangeTextIn affectedCharRange: NSRange,
            replacementString: String?,
        ) -> Bool { true }

        @MainActor
        func handleDrop(files: [URL], at insertionPoint: Int, in tv: NSTextView) {
            for url in files where Self.isImage(url: url) {
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
                    let mime = Self.mimeType(for: url)
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

        static func isImage(url: URL) -> Bool {
            let ext = url.pathExtension.lowercased()
            return ["png", "jpg", "jpeg", "gif", "webp", "heic"].contains(ext)
        }

        static func mimeType(for url: URL) -> String {
            switch url.pathExtension.lowercased() {
            case "png": return "image/png"
            case "jpg", "jpeg": return "image/jpeg"
            case "gif": return "image/gif"
            case "webp": return "image/webp"
            case "heic": return "image/heic"
            default: return "application/octet-stream"
            }
        }
    }
}

// MARK: - Drag-drop subview

/// We can't override NSTextView's drag handling cleanly through the SwiftUI
/// representable alone, so the toolbar exposes an "Insert image" button that
/// shows a file picker — covers the common path. Drop support is best-effort
/// via the coordinator's `handleDrop` if the user wires it in. Avoiding a
/// custom NSTextView subclass keeps this file shorter and tighter.

// MARK: - Slash menu UI

/// Observable backing the floating "/" command menu. Mutated only on the main
/// thread (from NSTextView delegate callbacks), so a plain ObservableObject.
final class SlashMenuModel: ObservableObject {
    @Published var blocks: [SlashBlock] = []
    @Published var selection: Int = 0
    var onPick: ((SlashBlock) -> Void)?
}

/// The list shown in the slash-menu panel. Uses system materials/labels so it
/// reads correctly in both light and dark appearances without app-theme access.
struct SlashMenuView: View {
    @ObservedObject var model: SlashMenuModel

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            if model.blocks.isEmpty {
                Text("No matching blocks")
                    .font(.system(size: 11)).foregroundColor(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 6)
            } else {
                ForEach(Array(model.blocks.enumerated()), id: \.element.id) { idx, block in
                    HStack(spacing: 8) {
                        Image(systemName: block.icon)
                            .font(.system(size: 12)).frame(width: 18)
                            .foregroundColor(idx == model.selection ? .accentColor : .secondary)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(block.title).font(.system(size: 12, weight: .medium)).foregroundColor(.primary)
                            Text(block.subtitle).font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                        }
                        Spacer(minLength: 12)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(idx == model.selection ? Color.accentColor.opacity(0.18) : Color.clear))
                    .contentShape(Rectangle())
                    .onTapGesture { model.onPick?(block) }
                    .onHover { if $0 { model.selection = idx } }
                }
            }
        }
        .padding(5)
        .frame(width: 248, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.primary.opacity(0.10)))
        .fixedSize(horizontal: false, vertical: true)
    }
}
