import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Controller surface shared between the editor view and its toolbar so the
/// same selection-mutating routines back both keyboard shortcuts and the
/// toolbar icon buttons. The editor view registers its NSTextView with the
/// controller on `makeNSView`; toolbar buttons call into the controller and
/// the controller drives the text view directly.
///
/// Split out of RichJournalEditor.swift.
@MainActor
final class JournalEditorController: ObservableObject {
    weak var textView: NSTextView?
    /// Closure invoked when an image is dropped or chosen via the toolbar.
    /// Implementation should upload the bytes and return a public URL
    /// (or nil on failure — the placeholder token gets cleared).
    var onUploadImage: ((Data, String, String) async -> String?)?
    /// Closure invoked by the right-click "Create to-do from selection" item,
    /// with the selected text. Wired by the host view to the productivity API.
    var onCreateTodo: ((String) -> Void)?
    /// Right-click "Add to calendar" — selected text → a dated to-do (today).
    var onAddToCalendar: ((String) -> Void)?

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

    /// MIME type for an image URL by extension. One table, shared with the
    /// drag-drop pipeline in `RichJournalEditor.Coordinator` — which had its own
    /// byte-identical copy before the split.
    ///
    /// `nonisolated` so the drop pipeline can call it off the main actor, which
    /// is where the Coordinator's copy lived.
    nonisolated static func imageMimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "gif": return "image/gif"
        case "webp": return "image/webp"
        case "heic": return "image/heic"
        default: return "application/octet-stream"
        }
    }

    /// Whether the editor will upload this file on drop / from the picker.
    nonisolated static func isImage(url: URL) -> Bool {
        ["png", "jpg", "jpeg", "gif", "webp", "heic"].contains(url.pathExtension.lowercased())
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
