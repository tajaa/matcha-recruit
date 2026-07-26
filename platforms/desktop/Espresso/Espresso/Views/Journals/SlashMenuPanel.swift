import AppKit
import SwiftUI

// MARK: - Slash menu
//
// The floating "/" command menu: its model, its SwiftUI list, and the NSPanel
// that hosts it. Split out of RichJournalEditor.Coordinator, which owned the
// panel lifecycle inline alongside text editing and drag-drop.

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

/// Owns the borderless floating NSPanel the slash menu lives in, plus the
/// "which query is live, over which character range" state. The editor decides
/// *what* a picked block does; this decides only *whether and where* the menu
/// is on screen.
///
/// Not `@MainActor`-annotated on purpose: it is driven entirely from
/// NSTextView delegate callbacks, matching the coordinator that used to own
/// this state directly.
final class SlashMenuPanel {
    private static let width: CGFloat = 248

    /// True while a "/query" is live and the panel is on screen.
    private(set) var isActive = false
    /// The `/query` character range in the text view, replaced on commit.
    private(set) var range = NSRange(location: 0, length: 0)

    /// Invoked when the user picks a block (click, Return, or Tab).
    var onPick: ((SlashBlock) -> Void)?

    private var panel: NSPanel?
    private var host: NSHostingView<SlashMenuView>?
    private var model: SlashMenuModel?

    deinit { panel?.orderOut(nil) }

    /// Filter `blocks` by `query` and show the panel under the caret. Dismisses
    /// and returns false when nothing matches.
    @discardableResult
    func show(blocks: [SlashBlock], query: String, range: NSRange, in tv: NSTextView) -> Bool {
        let q = query.lowercased()
        let filtered = q.isEmpty ? blocks : blocks.filter { b in
            b.title.lowercased().contains(q) || b.keywords.contains { $0.lowercased().contains(q) }
        }
        guard !filtered.isEmpty else { dismiss(); return false }
        self.range = range
        let model = ensureMenu()
        model.blocks = filtered
        if model.selection >= filtered.count { model.selection = 0 }
        position(in: tv, at: range.location)
        panel?.orderFront(nil)
        isActive = true
        return true
    }

    func dismiss() {
        guard isActive || panel != nil else { return }
        isActive = false
        panel?.orderOut(nil)
    }

    func moveSelection(_ delta: Int) {
        guard let m = model, !m.blocks.isEmpty else { return }
        let n = m.blocks.count
        m.selection = ((m.selection + delta) % n + n) % n
    }

    /// The highlighted block, or nil when the menu is empty/out of sync.
    var selectedBlock: SlashBlock? {
        guard let m = model, m.selection < m.blocks.count else { return nil }
        return m.blocks[m.selection]
    }

    // MARK: - Panel lifecycle

    private func ensureMenu() -> SlashMenuModel {
        if let m = model { return m }
        let m = SlashMenuModel()
        m.onPick = { [weak self] block in self?.onPick?(block) }
        let host = NSHostingView(rootView: SlashMenuView(model: m))
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: Self.width, height: 200),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered, defer: true,
        )
        panel.isFloatingPanel = true
        panel.level = .popUpMenu
        panel.hasShadow = true
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.contentView = host
        self.model = m
        self.host = host
        self.panel = panel
        return m
    }

    private func position(in tv: NSTextView, at charIndex: Int) {
        // firstRect returns the caret rect in SCREEN coordinates (y-up).
        let caretRect = tv.firstRect(
            forCharacterRange: NSRange(location: charIndex, length: 0), actualRange: nil,
        )
        let h = host?.fittingSize.height ?? 200
        let gap: CGFloat = 4
        let originX = caretRect.minX
        let originY = caretRect.minY - gap - h   // drop the panel just below the caret
        panel?.setFrame(NSRect(x: originX, y: originY, width: Self.width, height: max(h, 1)), display: true)
    }
}
