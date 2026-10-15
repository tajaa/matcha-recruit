import SwiftUI
import AppKit

/// A pane on the right whose width the person sets by dragging its left edge,
/// remembered under `storageKey`. Double-clicking the edge puts it back.
/// It never takes more than `maxWidth` (what the caller can spare beside its
/// own content), so widening it never pushes the window wider.
struct ResizableTrailingPane<Content: View>: View {
    @AppStorage private var width: Double
    private let defaultWidth: Double
    private let minWidth: Double
    private let maxWidth: Double
    private let content: () -> Content
    @State private var dragStart: Double?
    @State private var hovering = false
    /// The resize cursor is pushed: popped when the pointer leaves or the pane goes.
    @State private var cursorPushed = false

    init(storageKey: String, defaultWidth: Double, minWidth: Double = 340, maxWidth: Double,
         @ViewBuilder content: @escaping () -> Content) {
        _width = AppStorage(wrappedValue: defaultWidth, storageKey)
        self.defaultWidth = defaultWidth
        self.minWidth = minWidth
        self.maxWidth = maxWidth
        self.content = content
    }

    var body: some View {
        HStack(spacing: 0) {
            handle
            content().frame(width: Self.clamp(width, min: minWidth, max: maxWidth))
        }
    }

    private var handle: some View {
        Rectangle()
            .fill(Color.primary.opacity(hovering || dragStart != nil ? 0.18 : 0.08))
            .frame(width: 1)
            .padding(.horizontal, 3)
            .contentShape(Rectangle())
            .onHover { inside in
                hovering = inside
                setCursor(inside || dragStart != nil)
            }
            .onDisappear { setCursor(false) }
            .gesture(
                DragGesture(minimumDistance: 1, coordinateSpace: .global)
                    .onChanged { value in
                        let start = dragStart ?? Self.clamp(width, min: minWidth, max: maxWidth)
                        if dragStart == nil { dragStart = start }
                        // Mid-drag the pointer runs off the thin edge: keep the arrows.
                        NSCursor.resizeLeftRight.set()
                        // Dragging the edge left makes the pane wider.
                        width = Self.clamp(start - value.translation.width, min: minWidth, max: maxWidth)
                    }
                    .onEnded { _ in
                        dragStart = nil
                        if !hovering { setCursor(false); NSCursor.arrow.set() }
                    }
            )
            .onTapGesture(count: 2) { width = defaultWidth }
            .help("Drag to resize. Double-click to reset.")
    }

    /// Push the resize cursor once, pop it once: an unbalanced pop would take
    /// someone else's cursor, a missed one leaves the arrows on for good.
    private func setCursor(_ on: Bool) {
        if on && !cursorPushed {
            NSCursor.resizeLeftRight.push()
            cursorPushed = true
        } else if !on && cursorPushed {
            NSCursor.pop()
            cursorPushed = false
        }
    }

    /// `value` kept between `min` and `max`; `min` wins when there's no room.
    nonisolated static func clamp(_ value: Double, min: Double, max: Double) -> Double {
        Swift.max(min, Swift.min(value, Swift.max(min, max)))
    }
}
