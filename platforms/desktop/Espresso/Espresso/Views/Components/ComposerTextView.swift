import SwiftUI
import AppKit

/// AppKit-backed multi-line chat input.
///
/// Replaces `TextField(axis: .vertical)` in the chat composers. That control
/// is an `NSTextField` with wrapping enabled, and on macOS it has two
/// problems at chat-message sizes:
///
/// 1. It cannot scroll. Once the draft exceeds the `lineLimit` upper bound the
///    field stops growing and the caret goes off-screen, so typing "stops"
///    at roughly 6 lines (~400 characters at composer width).
/// 2. Every keystroke re-lays-out the whole field through the SwiftUI
///    text-field bridge, which gets visibly slow well before the cap.
///
/// `NSTextView` handles both natively: it keeps its own layout, scrolls inside
/// an `NSScrollView` once the content passes `maxLines`, and only reports a
/// height change to SwiftUI when the number of lines actually changes.
struct ComposerTextView: View {
    enum SubmitKey {
        /// ↵ sends, ⇧↵ inserts a newline (the AI chat composer).
        case returnSends
        /// ⌘↵ sends, ↵ inserts a newline (the channel composer).
        case commandReturnSends
    }

    @Binding var text: String
    var placeholder: String = ""
    var font: NSFont = .systemFont(ofSize: 14)
    var textColor: Color = .primary
    var placeholderColor: Color = Color.secondary.opacity(0.6)
    var minLines: Int = 1
    var maxLines: Int = 6
    var submitKey: SubmitKey = .returnSends
    var onSubmit: () -> Void = {}
    /// Called instead of the default paste when the pasteboard holds an image
    /// and no plain text. `nil` leaves image pastes to the text view (dropped).
    var onPasteImage: (() -> Void)? = nil

    var focusRequested: Binding<Bool> = .constant(false)

    @State private var contentHeight: CGFloat = 0

    private var lineHeight: CGFloat {
        // Same metric NSLayoutManager uses for a line of `font`.
        NSLayoutManager().defaultLineHeight(for: font).rounded(.up)
    }
    private var verticalInset: CGFloat { 2 }

    private var resolvedHeight: CGFloat {
        let minH = CGFloat(max(1, minLines)) * lineHeight + verticalInset * 2
        let maxH = CGFloat(max(minLines, maxLines)) * lineHeight + verticalInset * 2
        return min(max(contentHeight + verticalInset * 2, minH), maxH)
    }

    var body: some View {
        ComposerTextViewRepresentable(
            text: $text,
            contentHeight: $contentHeight,
            font: font,
            textColor: NSColor(textColor),
            verticalInset: verticalInset,
            submitKey: submitKey,
            onSubmit: onSubmit,
            onPasteImage: onPasteImage,
            focusRequested: focusRequested
        )
        .frame(height: resolvedHeight)
        .overlay(alignment: .topLeading) {
            if text.isEmpty {
                Text(placeholder)
                    .font(Font(font))
                    .foregroundColor(placeholderColor)
                    .padding(.top, verticalInset)
                    .padding(.leading, 5) // NSTextContainer.lineFragmentPadding
                    .allowsHitTesting(false)
            }
        }
    }
}

private struct ComposerTextViewRepresentable: NSViewRepresentable {
    @Environment(\.isEnabled) private var isEnabled
    @Binding var text: String
    @Binding var contentHeight: CGFloat
    let font: NSFont
    let textColor: NSColor
    let verticalInset: CGFloat
    let submitKey: ComposerTextView.SubmitKey
    let onSubmit: () -> Void
    let onPasteImage: (() -> Void)?
    @Binding var focusRequested: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.scrollerStyle = .overlay
        scrollView.verticalScrollElasticity = .none

        let textView = ComposerNSTextView()
        textView.delegate = context.coordinator
        textView.drawsBackground = false
        textView.isRichText = false
        textView.importsGraphics = false
        textView.allowsUndo = true
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.isContinuousSpellCheckingEnabled = true
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainerInset = NSSize(width: 0, height: verticalInset)
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: scrollView.contentSize.width,
            height: CGFloat.greatestFiniteMagnitude
        )
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.onReturn = { [weak coordinator = context.coordinator] flags in
            coordinator?.handleReturn(flags) ?? false
        }
        textView.onPasteImage = onPasteImage
        applyStyle(to: textView)
        textView.string = text

        scrollView.documentView = textView
        context.coordinator.textView = textView

        // Re-measure when the composer gets wider/narrower — line count changes
        // with wrap width, not just with text.
        scrollView.contentView.postsFrameChangedNotifications = true
        context.coordinator.frameObserver = NotificationCenter.default.addObserver(
            forName: NSView.frameDidChangeNotification,
            object: scrollView.contentView,
            queue: .main
        ) { [weak coordinator = context.coordinator] _ in
            coordinator?.measure()
        }
        DispatchQueue.main.async { context.coordinator.measure() }
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let textView = context.coordinator.textView else { return }
        applyStyle(to: textView)
        textView.onPasteImage = onPasteImage
        if focusRequested {
            DispatchQueue.main.async { [weak textView] in
                guard let textView, let window = textView.window else { return }
                if window.makeFirstResponder(textView) {
                    context.coordinator.parent.focusRequested = false
                }
            }
        }
        // Only push the binding down when it changed externally (seed / clear /
        // hard cap). During normal typing the coordinator already wrote this
        // exact string up, and resetting it would move the caret to the end.
        if textView.string != text {
            textView.string = text
            // Defer: we're inside a SwiftUI update, and measure() writes @State.
            DispatchQueue.main.async { [weak coordinator = context.coordinator] in
                coordinator?.measure()
            }
        }
    }

    static func dismantleNSView(_ scrollView: NSScrollView, coordinator: Coordinator) {
        if let obs = coordinator.frameObserver {
            NotificationCenter.default.removeObserver(obs)
        }
    }

    private func applyStyle(to textView: NSTextView) {
        textView.isEditable = isEnabled
        if textView.font != font { textView.font = font }
        if textView.textColor != textColor {
            textView.textColor = textColor
            textView.insertionPointColor = textColor
        }
        textView.typingAttributes = [.font: font, .foregroundColor: textColor]
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ComposerTextViewRepresentable
        weak var textView: ComposerNSTextView?
        var frameObserver: NSObjectProtocol?

        init(_ parent: ComposerTextViewRepresentable) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            parent.text = textView.string
            measure()
        }

        func handleReturn(_ flags: NSEvent.ModifierFlags) -> Bool {
            guard parent.isEnabled else { return true }
            switch parent.submitKey {
            case .returnSends:
                // ⇧↵ (and ⌥↵) fall through so the newline lands at the caret.
                if flags.contains(.shift) || flags.contains(.option) { return false }
                parent.onSubmit()
                return true
            case .commandReturnSends:
                guard flags.contains(.command) else { return false }
                parent.onSubmit()
                return true
            }
        }

        /// Reports the laid-out text height. Cheap: `usedRect` reads the
        /// layout NSTextView already did for drawing; nothing is re-typeset.
        func measure() {
            guard let textView, let lm = textView.layoutManager, let tc = textView.textContainer else { return }
            lm.ensureLayout(for: tc)
            var h = lm.usedRect(for: tc).height
            if textView.string.isEmpty {
                h = lm.defaultLineHeight(for: parent.font).rounded(.up)
            }
            if abs(h - parent.contentHeight) > 0.5 {
                parent.contentHeight = h
            }
        }
    }
}

private final class ComposerNSTextView: NSTextView {
    /// Return `true` to swallow the key. Receives the device-independent flags.
    var onReturn: ((NSEvent.ModifierFlags) -> Bool)?
    var onPasteImage: (() -> Void)?

    private static let returnKeyCode: UInt16 = 36
    private static let keypadEnterKeyCode: UInt16 = 76

    private func isReturn(_ event: NSEvent) -> Bool {
        event.keyCode == Self.returnKeyCode || event.keyCode == Self.keypadEnterKeyCode
    }

    override func keyDown(with event: NSEvent) {
        if isReturn(event), let onReturn,
           onReturn(event.modifierFlags.intersection(.deviceIndependentFlagsMask)) {
            return
        }
        super.keyDown(with: event)
    }

    /// ⌘↵ arrives as a key equivalent before `keyDown`; claim it here so the
    /// window's menu / SwiftUI shortcut chain doesn't eat it first.
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if isReturn(event), event.modifierFlags.contains(.command), let onReturn,
           onReturn(event.modifierFlags.intersection(.deviceIndependentFlagsMask)) {
            return true
        }
        return super.performKeyEquivalent(with: event)
    }

    override func paste(_ sender: Any?) {
        let pb = NSPasteboard.general
        let hasText = pb.string(forType: .string) != nil
        let hasImage = pb.canReadObject(forClasses: [NSImage.self], options: nil)
        if hasImage, !hasText, let onPasteImage {
            onPasteImage()
            return
        }
        // Rich pastes flatten to plain text (isRichText is false), but be
        // explicit so file promises / attachments never land as attachments.
        pasteAsPlainText(sender)
    }
}
