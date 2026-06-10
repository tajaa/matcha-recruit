import AppKit
import SwiftUI

// Custom text attribute tagging each paragraph with its screenplay element.
extension NSAttributedString.Key {
    static let spElement = NSAttributedString.Key("spElement")
}

// MARK: - Screenplay formatting metrics

/// Industry-style paragraph metrics (in points, tuned for the on-screen editor
/// at 12pt Courier). Cached per element so the layout pass never allocates a
/// paragraph style mid-keystroke.
enum ScreenplayFormat {
    static func font(size: CGFloat, bold: Bool = false) -> NSFont {
        let name = bold ? "Courier-Bold" : "Courier"
        return NSFont(name: name, size: size)
            ?? .monospacedSystemFont(ofSize: size, weight: bold ? .bold : .regular)
    }

    private static var styleCache: [ScreenplayElement: NSParagraphStyle] = [:]

    static func paragraphStyle(for element: ScreenplayElement) -> NSParagraphStyle {
        if let cached = styleCache[element] { return cached }
        let p = NSMutableParagraphStyle()
        p.lineSpacing = 1
        switch element {
        case .sceneHeading:
            p.paragraphSpacingBefore = 16
        case .action, .shot:
            p.paragraphSpacingBefore = 10
        case .character:
            p.paragraphSpacingBefore = 10
            p.firstLineHeadIndent = 180; p.headIndent = 180
        case .parenthetical:
            p.firstLineHeadIndent = 150; p.headIndent = 150; p.tailIndent = -150
        case .dialogue:
            p.firstLineHeadIndent = 110; p.headIndent = 110; p.tailIndent = -110
        case .transition:
            p.paragraphSpacingBefore = 10; p.alignment = .right
        case .centered:
            p.paragraphSpacingBefore = 10; p.alignment = .center
        case .section:
            p.paragraphSpacingBefore = 16
        case .synopsis:
            p.paragraphSpacingBefore = 4
        case .pageBreak:
            p.paragraphSpacingBefore = 10; p.alignment = .center
        }
        let immutable = p.copy() as! NSParagraphStyle
        styleCache[element] = immutable
        return immutable
    }

    static func attributes(for element: ScreenplayElement, size: CGFloat, color: NSColor) -> [NSAttributedString.Key: Any] {
        let bold = (element == .sceneHeading || element == .section)
        let fg: NSColor = (element == .section || element == .synopsis) ? color.withAlphaComponent(0.6) : color
        return [
            .font: font(size: size, bold: bold),
            .foregroundColor: fg,
            .paragraphStyle: paragraphStyle(for: element),
            .spElement: element.rawValue,
        ]
    }
}

// MARK: - Controller (shared between the SwiftUI chrome and the text view)

/// Bridges the SwiftUI element bar / title-page sheet and the NSTextView. Holds
/// the live title page and the caret's current element so the chrome can react.
/// Not `@MainActor`: every mutation already happens on the main thread (text
/// view delegate callbacks + SwiftUI actions), and the nonisolated NSTextView
/// coordinator needs to write these without hopping actors.
final class ScreenplayController: ObservableObject {
    weak var textView: NSTextView?
    @Published var currentElement: ScreenplayElement = .sceneHeading
    @Published var titlePage = ScreenplayTitlePage()
    /// Set by the representable; lets the chrome push an element onto the caret.
    var applyElement: ((ScreenplayElement) -> Void)?
    /// Re-serialize the document (after a title-page edit) and push to the binding.
    var reserialize: (() -> Void)?
}

// MARK: - NSTextView wrapper

/// WYSIWYG screenplay editor. Each paragraph is one `ScreenplayLine`; its
/// element is stored as a text attribute that drives Courier formatting +
/// uppercasing. Tab cycles the current element, Return smart-advances to the
/// next, and the whole thing serializes to/from Fountain in the bound `text`.
struct ScreenplayNSEditor: NSViewRepresentable {
    @Binding var text: String
    @ObservedObject var controller: ScreenplayController
    let fontSize: CGFloat
    let textColor: NSColor

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        guard let tv = scroll.documentView as? NSTextView else { return scroll }
        tv.delegate = context.coordinator
        tv.isRichText = true
        tv.allowsUndo = true
        tv.isAutomaticQuoteSubstitutionEnabled = false
        tv.isAutomaticDashSubstitutionEnabled = false
        tv.isAutomaticTextReplacementEnabled = false
        tv.isAutomaticSpellingCorrectionEnabled = false
        tv.textContainerInset = NSSize(width: 12, height: 14)
        tv.backgroundColor = .clear
        tv.drawsBackground = false
        tv.insertionPointColor = textColor
        context.coordinator.textView = tv
        controller.textView = tv
        controller.applyElement = { [weak coordinator = context.coordinator] e in
            coordinator?.applyElementToCurrentParagraph(e)
        }
        controller.reserialize = { [weak coordinator = context.coordinator] in
            coordinator?.pushSerialized()
        }
        context.coordinator.rebuild(from: text)
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let tv = scroll.documentView as? NSTextView else { return }
        // Only rebuild when the incoming text isn't what we last wrote out.
        if text != context.coordinator.lastSerialized {
            context.coordinator.rebuild(from: text)
        }
        tv.insertionPointColor = textColor
    }

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ScreenplayNSEditor
        weak var textView: NSTextView?
        var lastSerialized = ""
        private var isProgrammatic = false

        // MARK: Slash menu state (same NSPanel pattern as RichJournalEditor)
        private var slashActive = false
        private var slashRange = NSRange(location: 0, length: 0)
        private var slashPanel: NSPanel?
        private var slashHost: NSHostingView<ScreenplaySlashMenuView>?
        private var slashModel: ScreenplaySlashModel?

        init(parent: ScreenplayNSEditor) { self.parent = parent }

        private var size: CGFloat { parent.fontSize }
        private var color: NSColor { parent.textColor }

        // MARK: Load (Fountain → attributed body)

        func rebuild(from fountain: String) {
            guard let tv = textView else { return }
            let doc = FountainParser.parse(fountain)
            let attr = NSMutableAttributedString()
            for line in doc.lines {
                let element = line.element
                let shown = element.isUppercased ? line.text.uppercased() : line.text
                attr.append(NSAttributedString(
                    string: shown + "\n",
                    attributes: ScreenplayFormat.attributes(for: element, size: size, color: color),
                ))
            }
            isProgrammatic = true
            tv.textStorage?.setAttributedString(attr)
            isProgrammatic = false
            lastSerialized = fountain
            // Defer controller (@Published) updates: rebuild can run from
            // updateNSView, and publishing during a view update is disallowed.
            let tp = doc.titlePage
            let element = elementAtCaret(tv)
            let controller = parent.controller
            DispatchQueue.main.async {
                if controller.titlePage != tp { controller.titlePage = tp }
                if controller.currentElement != element { controller.currentElement = element }
            }
        }

        // MARK: Serialize (attributed body → Fountain)

        func currentDocument(_ tv: NSTextView) -> ScreenplayDocument {
            guard let storage = tv.textStorage else {
                return ScreenplayDocument(titlePage: parent.controller.titlePage, lines: [])
            }
            let ns = tv.string as NSString
            var lines: [ScreenplayLine] = []
            ns.enumerateSubstrings(in: NSRange(location: 0, length: ns.length), options: [.byParagraphs]) { sub, subRange, _, _ in
                let text = sub ?? ""
                var element = ScreenplayElement.action
                if subRange.length > 0,
                   let raw = storage.attribute(.spElement, at: subRange.location, effectiveRange: nil) as? String,
                   let e = ScreenplayElement(rawValue: raw) {
                    element = e
                }
                lines.append(ScreenplayLine(element: element, text: text))
            }
            return ScreenplayDocument(titlePage: parent.controller.titlePage, lines: lines)
        }

        func pushSerialized() {
            guard let tv = textView else { return }
            let fountain = FountainParser.serialize(currentDocument(tv))
            lastSerialized = fountain
            parent.text = fountain
        }

        // MARK: Editing helpers

        private func paragraphRange(_ tv: NSTextView) -> NSRange {
            (tv.string as NSString).paragraphRange(for: tv.selectedRange())
        }

        func elementAtCaret(_ tv: NSTextView) -> ScreenplayElement {
            guard let storage = tv.textStorage else { return .action }
            let pr = paragraphRange(tv)
            let probe = pr.length > 0 ? pr.location : max(0, pr.location - 1)
            if probe < storage.length,
               let raw = storage.attribute(.spElement, at: probe, effectiveRange: nil) as? String,
               let e = ScreenplayElement(rawValue: raw) {
                return e
            }
            if let raw = tv.typingAttributes[.spElement] as? String, let e = ScreenplayElement(rawValue: raw) {
                return e
            }
            return .action
        }

        /// Apply an element's formatting to the current paragraph (restyle the
        /// run, uppercase if needed, set typing attributes) and push the change.
        func applyElementToCurrentParagraph(_ element: ScreenplayElement) {
            guard let tv = textView, let storage = tv.textStorage else { return }
            let pr = paragraphRange(tv)
            let attrs = ScreenplayFormat.attributes(for: element, size: size, color: color)
            isProgrammatic = true
            if pr.length > 0 {
                storage.setAttributes(attrs, range: pr)
                if element.isUppercased {
                    let ns = tv.string as NSString
                    let body = ns.substring(with: pr)
                    let upper = body.replacingOccurrences(of: "\n", with: "") .uppercased()
                    let hasNewline = body.hasSuffix("\n")
                    let replacement = upper + (hasNewline ? "\n" : "")
                    if replacement != body, tv.shouldChangeText(in: pr, replacementString: replacement) {
                        storage.replaceCharacters(in: pr, with: NSAttributedString(string: replacement, attributes: attrs))
                        tv.didChangeText()
                    }
                }
            }
            tv.typingAttributes = attrs
            isProgrammatic = false
            parent.controller.currentElement = element
            pushSerialized()
        }

        private func setTypingElement(_ element: ScreenplayElement, _ tv: NSTextView) {
            tv.typingAttributes = ScreenplayFormat.attributes(for: element, size: size, color: color)
            parent.controller.currentElement = element
        }

        private func updateCurrentElement(_ tv: NSTextView) {
            parent.controller.currentElement = elementAtCaret(tv)
        }

        // MARK: NSTextViewDelegate

        func textDidChange(_ notification: Notification) {
            guard !isProgrammatic, let tv = notification.object as? NSTextView else { return }
            // Live-uppercase the edited paragraph when its element demands it.
            let element = elementAtCaret(tv)
            if element.isUppercased { uppercaseCurrentParagraph(tv) }
            pushSerialized()
            updateSlashMenu(tv)
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard !isProgrammatic, let tv = notification.object as? NSTextView else { return }
            updateCurrentElement(tv)
            if slashActive { updateSlashMenu(tv) }   // caret left the "/query" → dismiss
        }

        // Editor lost first responder (clicked away, switched view) → don't
        // leave a detached slash panel floating.
        func textDidEndEditing(_ notification: Notification) {
            dismissSlash()
        }

        func textView(_ tv: NSTextView, doCommandBy selector: Selector) -> Bool {
            // While the slash menu is open, arrows/Return/Tab/Escape drive it.
            if slashActive {
                switch selector {
                case #selector(NSResponder.moveDown(_:)):    moveSlashSelection(1);  return true
                case #selector(NSResponder.moveUp(_:)):      moveSlashSelection(-1); return true
                case #selector(NSResponder.insertNewline(_:)),
                     #selector(NSResponder.insertTab(_:)):   commitSlashSelection(); return true
                case #selector(NSResponder.cancelOperation(_:)): dismissSlash();     return true
                default: break
                }
            }
            switch selector {
            case #selector(NSResponder.insertTab(_:)):
                let next = elementAtCaret(tv).tabCycle
                applyElementToCurrentParagraph(next)
                return true
            case #selector(NSResponder.insertNewline(_:)):
                handleReturn(tv)
                return true
            default:
                return false
            }
        }

        // MARK: Slash menu driving — "/scene", "/character", … convert the
        // current line to that element (Final Draft / Scrivener style); the
        // existing Return flow then auto-advances (character → dialogue, …).

        /// Note: no `.shot`/`.section`/`.synopsis` — mirrors the element bar
        /// (Fountain can't round-trip a shot; organizational layers stay
        /// out of the quick menu).
        private static let slashItems: [ScreenplaySlashItem] = [
            .init(element: .sceneHeading, icon: "film",
                  subtitle: "INT. / EXT. slugline", keywords: ["scene", "heading", "int", "ext", "slug"]),
            .init(element: .character, icon: "person.fill",
                  subtitle: "Cue — Return drops into dialogue", keywords: ["character", "cue", "name", "who"]),
            .init(element: .dialogue, icon: "text.bubble",
                  subtitle: "What they say", keywords: ["dialogue", "speech", "line", "say"]),
            .init(element: .parenthetical, icon: "parentheses",
                  subtitle: "(beat), (wryly)…", keywords: ["parenthetical", "paren", "beat", "wryly"]),
            .init(element: .action, icon: "text.alignleft",
                  subtitle: "Description / stage direction", keywords: ["action", "description", "direction"]),
            .init(element: .transition, icon: "arrow.right.to.line",
                  subtitle: "CUT TO:, FADE OUT.", keywords: ["transition", "cut", "fade", "dissolve"]),
            .init(element: .centered, icon: "text.aligncenter",
                  subtitle: "Centered text", keywords: ["centered", "center", "title"]),
        ]

        /// Recompute the live "/query" before the caret and show/refresh the
        /// floating menu, or dismiss when there's no active trigger.
        private func updateSlashMenu(_ tv: NSTextView) {
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
            // Only trigger at the start of a line — slash mid-sentence is text
            // (e.g. "24/7" in action), not a command.
            let boundaryOK: Bool = slashIdx == 0 || {
                let p = ns.substring(with: NSRange(location: slashIdx - 1, length: 1))
                return p == "\n"
            }()
            guard boundaryOK else { dismissSlash(); return }
            let query = ns.substring(with: NSRange(location: slashIdx + 1, length: caret - slashIdx - 1))
            showSlash(tv: tv, query: query, range: NSRange(location: slashIdx, length: caret - slashIdx))
        }

        private func showSlash(tv: NSTextView, query: String, range: NSRange) {
            let q = query.lowercased()
            let filtered = q.isEmpty ? Self.slashItems : Self.slashItems.filter { item in
                item.title.lowercased().contains(q) || item.keywords.contains { $0.hasPrefix(q) || $0.contains(q) }
            }
            guard !filtered.isEmpty else { dismissSlash(); return }
            slashRange = range
            let model = ensureSlashMenu()
            model.items = filtered
            if model.selection >= filtered.count { model.selection = 0 }
            positionSlashPanel(tv: tv, at: range.location)
            slashPanel?.orderFront(nil)
            slashActive = true
        }

        private func ensureSlashMenu() -> ScreenplaySlashModel {
            if let m = slashModel { return m }
            let m = ScreenplaySlashModel()
            m.onPick = { [weak self] item in self?.commitSlash(item) }
            let host = NSHostingView(rootView: ScreenplaySlashMenuView(model: m))
            let panel = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: 264, height: 200),
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
            slashPanel?.setFrame(
                NSRect(x: caretRect.minX, y: caretRect.minY - gap - h, width: 264, height: max(h, 1)),
                display: true,
            )
        }

        private func moveSlashSelection(_ delta: Int) {
            guard let m = slashModel, !m.items.isEmpty else { return }
            let n = m.items.count
            m.selection = ((m.selection + delta) % n + n) % n
        }

        private func commitSlashSelection() {
            guard let m = slashModel, m.selection < m.items.count else { return }
            commitSlash(m.items[m.selection])
        }

        private func commitSlash(_ item: ScreenplaySlashItem) {
            MainActor.assumeIsolated {
                guard let tv = textView else { dismissSlash(); return }
                let ns = tv.string as NSString
                let r = slashRange
                guard r.location >= 0, r.location + r.length <= ns.length else { dismissSlash(); return }
                // Strip the "/query", then convert the (now bare) paragraph.
                if tv.shouldChangeText(in: r, replacementString: "") {
                    tv.textStorage?.replaceCharacters(in: r, with: "")
                    tv.didChangeText()
                }
                tv.setSelectedRange(NSRange(location: r.location, length: 0))
                dismissSlash()
                applyElementToCurrentParagraph(item.element)
            }
        }

        private func dismissSlash() {
            guard slashActive || slashPanel != nil else { return }
            slashActive = false
            slashPanel?.orderOut(nil)
        }

        private func handleReturn(_ tv: NSTextView) {
            let current = elementAtCaret(tv)
            let next = current.afterReturn
            // Insert the paragraph break carrying the *next* element's attributes
            // so the new (empty) paragraph is already styled.
            let attrs = ScreenplayFormat.attributes(for: next, size: size, color: color)
            let sel = tv.selectedRange()
            if tv.shouldChangeText(in: sel, replacementString: "\n") {
                tv.textStorage?.replaceCharacters(in: sel, with: NSAttributedString(string: "\n", attributes: attrs))
                tv.didChangeText()
            }
            setTypingElement(next, tv)
            pushSerialized()
        }

        private func uppercaseCurrentParagraph(_ tv: NSTextView) {
            guard let storage = tv.textStorage else { return }
            let pr = paragraphRange(tv)
            guard pr.length > 0 else { return }
            let ns = tv.string as NSString
            let body = ns.substring(with: pr)
            let hadNewline = body.hasSuffix("\n")
            let core = hadNewline ? String(body.dropLast()) : body
            let upper = core.uppercased()
            guard upper != core else { return }
            let caret = tv.selectedRange()
            let replacement = upper + (hadNewline ? "\n" : "")
            let element = elementAtCaret(tv)
            let attrs = ScreenplayFormat.attributes(for: element, size: size, color: color)
            isProgrammatic = true
            if tv.shouldChangeText(in: pr, replacementString: replacement) {
                storage.replaceCharacters(in: pr, with: NSAttributedString(string: replacement, attributes: attrs))
                tv.didChangeText()
            }
            tv.setSelectedRange(caret)
            isProgrammatic = false
        }
    }
}

// MARK: - Public SwiftUI editor (element bar + text view + title page)

/// The screenplay document editor used by `JournalDetailView` when the journal
/// kind is `.screenplay`. Combines the element bar, the WYSIWYG text view, and
/// the title-page sheet; the bound `text` is Fountain.
struct ScreenplayDocEditor: View {
    @Binding var text: String
    var fontSize: CGFloat = 13
    var textColor: Color = .primary

    @StateObject private var controller = ScreenplayController()
    @State private var showTitlePage = false
    @State private var pageView = false
    @State private var pages: [ScreenplayPage] = []

    // Note: no `.shot` — Fountain has no shot syntax, so a shot element can't
    // round-trip; shots are written as all-caps action, which Fountain handles.
    private let barElements: [ScreenplayElement] = [
        .sceneHeading, .action, .character, .parenthetical, .dialogue, .transition, .centered,
    ]

    var body: some View {
        VStack(spacing: 0) {
            elementBar
            Divider().opacity(0.2)
            if pageView {
                ScrollView([.vertical, .horizontal]) {
                    VStack(spacing: 18) {
                        ForEach(pages) { ScreenplayPageView(page: $0) }
                    }
                    .padding(24)
                    .frame(maxWidth: .infinity)
                }
                .background(Color(white: 0.22))
            } else {
                ScreenplayNSEditor(
                    text: $text,
                    controller: controller,
                    fontSize: max(fontSize, 13),
                    textColor: NSColor(textColor),
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .sheet(isPresented: $showTitlePage) { titlePageSheet }
        .onChange(of: text) { _, _ in if pageView { recomputePages() } }
    }

    private func recomputePages() {
        pages = ScreenplayPaginator.paginate(FountainParser.parse(text))
    }

    private var elementBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                if !pageView {
                    ForEach(barElements, id: \.self) { e in
                        Button { controller.applyElement?(e) } label: {
                            Text(e.displayName)
                                .font(.system(size: 10, weight: controller.currentElement == e ? .semibold : .regular))
                                .padding(.horizontal, 8).padding(.vertical, 4)
                                .background(RoundedRectangle(cornerRadius: 5)
                                    .fill(controller.currentElement == e ? Color.accentColor.opacity(0.22) : Color.primary.opacity(0.06)))
                                .foregroundColor(controller.currentElement == e ? .accentColor : .primary.opacity(0.8))
                        }
                        .buttonStyle(.plain)
                        .help("\(e.displayName) — Tab cycles, Return advances")
                    }
                    Divider().frame(height: 16)
                    Button { showTitlePage = true } label: {
                        Label("Title Page", systemImage: "doc.text")
                            .font(.system(size: 10, weight: .medium))
                            .padding(.horizontal, 8).padding(.vertical, 4)
                    }
                    .buttonStyle(.plain)
                }
                Button {
                    pageView.toggle()
                    if pageView { recomputePages() }
                } label: {
                    Label(pageView ? "Edit" : "Page View", systemImage: pageView ? "pencil" : "doc.plaintext")
                        .font(.system(size: 10, weight: .medium))
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(RoundedRectangle(cornerRadius: 5)
                            .fill(pageView ? Color.accentColor.opacity(0.22) : Color.primary.opacity(0.06)))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
        }
    }

    private var titlePageSheet: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Title Page").font(.system(size: 15, weight: .semibold))
            Group {
                titleField("Title", text: Binding(get: { controller.titlePage.title }, set: { controller.titlePage.title = $0 }))
                titleField("Credit", text: Binding(get: { controller.titlePage.credit }, set: { controller.titlePage.credit = $0 }))
                titleField("Author", text: Binding(get: { controller.titlePage.author }, set: { controller.titlePage.author = $0 }))
                titleField("Source", text: Binding(get: { controller.titlePage.source }, set: { controller.titlePage.source = $0 }))
                titleField("Draft date", text: Binding(get: { controller.titlePage.draftDate }, set: { controller.titlePage.draftDate = $0 }))
                titleField("Contact", text: Binding(get: { controller.titlePage.contact }, set: { controller.titlePage.contact = $0 }))
            }
            HStack {
                Spacer()
                Button("Done") {
                    controller.reserialize?()
                    showTitlePage = false
                }
                .keyboardShortcut(.return)
            }
        }
        .padding(20)
        .frame(width: 380)
    }

    private func titleField(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 10)).foregroundColor(.secondary)
            TextField("", text: text).textFieldStyle(.roundedBorder)
        }
    }
}

// MARK: - On-screen page view

/// A single paginated US-Letter page, rendered Courier-12 with industry indents.
/// Mirrors the PDF layout so the writer previews exactly what exports.
struct ScreenplayPageView: View {
    let page: ScreenplayPage
    private let courier = Font.custom("Courier", size: 12)

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(page.number > 1 ? "\(page.number)." : "")
                .font(courier).foregroundColor(.black.opacity(0.5))
                .frame(maxWidth: ScreenplayPageMetrics.pageWidth - ScreenplayPageMetrics.marginRight, alignment: .trailing)
                .padding(.bottom, 18)
            ForEach(Array(page.lines.enumerated()), id: \.offset) { _, line in
                row(line)
            }
            Spacer(minLength: 0)
        }
        .padding(.top, 48)
        .frame(width: ScreenplayPageMetrics.pageWidth,
               height: ScreenplayPageMetrics.pageHeight, alignment: .topLeading)
        .background(Color.white)
        .overlay(Rectangle().stroke(Color.black.opacity(0.10)))
        .shadow(radius: 3)
    }

    @ViewBuilder
    private func row(_ line: ScreenplayPageLine) -> some View {
        if line.isBlank {
            Color.clear.frame(height: ScreenplayPageMetrics.lineHeight)
        } else {
            ZStack(alignment: .topLeading) {
                if let scene = line.sceneNumber {
                    Text(scene).font(courier).foregroundColor(.black.opacity(0.55))
                        .padding(.leading, 44)
                }
                Text(line.text)
                    .font(courier)
                    .fontWeight(line.element == .sceneHeading ? .bold : .regular)
                    .foregroundColor(.black)
                    .frame(width: ScreenplayPageMetrics.width(line.element), alignment: alignment(line.element))
                    .padding(.leading, ScreenplayPageMetrics.leftInset(line.element))
            }
            .frame(height: ScreenplayPageMetrics.lineHeight, alignment: .topLeading)
        }
    }

    private func alignment(_ e: ScreenplayElement) -> Alignment {
        switch e {
        case .transition: return .trailing
        case .centered:   return .center
        default:          return .leading
        }
    }
}

// MARK: - Slash menu (element quick-insert)

/// One row in the screenplay slash menu — "/scene", "/character", ….
struct ScreenplaySlashItem: Identifiable, Hashable {
    let element: ScreenplayElement
    let icon: String
    let subtitle: String
    let keywords: [String]
    var id: String { element.rawValue }
    var title: String { element.displayName }
}

final class ScreenplaySlashModel: ObservableObject {
    @Published var items: [ScreenplaySlashItem] = []
    @Published var selection: Int = 0
    var onPick: ((ScreenplaySlashItem) -> Void)?
}

/// Floating completion list. System materials/labels so it reads correctly in
/// both appearances without app-theme access (same as the journal slash menu).
struct ScreenplaySlashMenuView: View {
    @ObservedObject var model: ScreenplaySlashModel

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            if model.items.isEmpty {
                Text("No matching elements")
                    .font(.system(size: 11)).foregroundColor(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 6)
            } else {
                ForEach(Array(model.items.enumerated()), id: \.element.id) { idx, item in
                    HStack(spacing: 8) {
                        Image(systemName: item.icon)
                            .font(.system(size: 12)).frame(width: 18)
                            .foregroundColor(idx == model.selection ? .accentColor : .secondary)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.title).font(.system(size: 12, weight: .medium)).foregroundColor(.primary)
                            Text(item.subtitle).font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                        }
                        Spacer(minLength: 12)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(idx == model.selection ? Color.accentColor.opacity(0.18) : Color.clear))
                    .contentShape(Rectangle())
                    .onTapGesture { model.onPick?(item) }
                    .onHover { if $0 { model.selection = idx } }
                }
            }
        }
        .padding(5)
        .frame(width: 264, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color.primary.opacity(0.10)))
        .fixedSize(horizontal: false, vertical: true)
    }
}
