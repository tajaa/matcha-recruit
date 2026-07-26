import AppKit
import Foundation

// MARK: - Live markdown styler

/// Applies live formatting to a markdown source NSTextView: headings, bold,
/// italic, strikethrough, highlight, inline code, blockquotes, list markers and
/// links render in place while the syntax markers stay (dimmed, Bear/iA style).
/// Pure attribute pass — never mutates the characters, so the stored text stays
/// plain markdown and there are no caret/undo surprises.
///
/// Split out of RichJournalEditor.swift.
enum MarkdownStyler {
    private static func rx(_ p: String) -> NSRegularExpression {
        // Patterns are constant + valid; `try!` is fine and compiles once.
        try! NSRegularExpression(pattern: p, options: [.anchorsMatchLines])
    }

    // Block (per-line, ^/$ match line bounds via .anchorsMatchLines).
    private static let reHeading  = rx(#"^(#{1,3})([ \t]+)(.*)$"#)
    private static let reQuote    = rx(#"^([ \t]*>)([ \t]+)(.*)$"#)
    private static let reTodo     = rx(#"^([ \t]*[-*][ \t]+\[([ xX])\])([ \t]+)(.*)$"#)
    private static let reBullet   = rx(#"^([ \t]*[-*])([ \t]+)(?!\[[ xX]\])(.*)$"#)
    private static let reNumbered = rx(#"^(\d+\.)([ \t]+)(.*)$"#)
    private static let reOutline  = rx(#"^([ \t]+[0-9A-Za-z]+\.)([ \t]+)(.*)$"#)  // indented = alpha/roman/decimal sub-items
    private static let reDivider  = rx(#"^[ \t]*(?:---|\*\*\*)[ \t]*$"#)
    // Inline.
    private static let reBold1    = rx(#"\*\*([^*\n]+)\*\*"#)
    private static let reBold2    = rx(#"__([^_\n]+)__"#)
    private static let reItalic1  = rx(#"(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)"#)
    private static let reItalic2  = rx(#"(?<![_\w])_(?!_)([^_\n]+)_(?![_\w])"#)
    private static let reStrike   = rx(#"~~([^~\n]+)~~"#)
    private static let reHighlight = rx(#"==([^=\n]+)=="#)
    private static let reCode     = rx(#"`([^`\n]+)`"#)
    private static let reLink     = rx(#"\[([^\]\n]+)\]\(([^)\n]+)\)"#)

    static func apply(to storage: NSTextStorage, fullText ns: NSString, baseFont: NSFont, textColor: NSColor, lineSpacing: CGFloat) {
        let full = NSRange(location: 0, length: ns.length)
        let para = NSMutableParagraphStyle(); para.lineSpacing = lineSpacing
        let dim = textColor.withAlphaComponent(0.30)
        let secondary = textColor.withAlphaComponent(0.72)
        let fm = NSFontManager.shared
        let boldFont = fm.convert(baseFont, toHaveTrait: .boldFontMask)
        let monoFont = NSFont.monospacedSystemFont(ofSize: baseFont.pointSize, weight: .regular)

        storage.beginEditing()
        defer { storage.endEditing() }
        storage.setAttributes([.font: baseFont, .foregroundColor: textColor, .paragraphStyle: para], range: full)

        // ── Block styles ──
        each(reHeading, ns, full) { m in
            let level = m.range(at: 1).length
            let size = baseFont.pointSize + (level == 1 ? 6 : level == 2 ? 3 : 1)
            let hFont = fm.convert(NSFont(descriptor: baseFont.fontDescriptor, size: size) ?? baseFont, toHaveTrait: .boldFontMask)
            storage.addAttribute(.font, value: hFont, range: m.range)
            storage.addAttribute(.foregroundColor, value: dim, range: m.range(at: 1))
        }
        each(reQuote, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 3))
            storage.addAttribute(.obliqueness, value: 0.18, range: m.range(at: 3))
            storage.addAttribute(.foregroundColor, value: dim, range: m.range(at: 1))
        }
        each(reTodo, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 1))
            if ns.substring(with: m.range(at: 2)).lowercased() == "x" {
                storage.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: m.range(at: 4))
                storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 4))
            }
        }
        each(reBullet, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 1))
        }
        each(reNumbered, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 1))
        }
        each(reOutline, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: secondary, range: m.range(at: 1))
        }
        each(reDivider, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: dim, range: m.range)
        }

        // ── Inline styles ──
        each(reBold1, ns, full) { m in storage.addAttribute(.font, value: boldFont, range: m.range); dimEdges(storage, m.range, 2, dim) }
        each(reBold2, ns, full) { m in storage.addAttribute(.font, value: boldFont, range: m.range); dimEdges(storage, m.range, 2, dim) }
        each(reItalic1, ns, full) { m in storage.addAttribute(.obliqueness, value: 0.18, range: m.range(at: 1)); dimEdges(storage, m.range, 1, dim) }
        each(reItalic2, ns, full) { m in storage.addAttribute(.obliqueness, value: 0.18, range: m.range(at: 1)); dimEdges(storage, m.range, 1, dim) }
        each(reStrike, ns, full) { m in
            storage.addAttribute(.strikethroughStyle, value: NSUnderlineStyle.single.rawValue, range: m.range(at: 1))
            dimEdges(storage, m.range, 2, dim)
        }
        each(reHighlight, ns, full) { m in
            storage.addAttribute(.backgroundColor, value: NSColor.systemYellow.withAlphaComponent(0.30), range: m.range(at: 1))
            dimEdges(storage, m.range, 2, dim)
        }
        each(reCode, ns, full) { m in
            storage.addAttribute(.font, value: monoFont, range: m.range)
            storage.addAttribute(.backgroundColor, value: NSColor.gray.withAlphaComponent(0.18), range: m.range(at: 1))
            dimEdges(storage, m.range, 1, dim)
        }
        each(reLink, ns, full) { m in
            storage.addAttribute(.foregroundColor, value: dim, range: m.range)
            storage.addAttribute(.foregroundColor, value: NSColor.controlAccentColor, range: m.range(at: 1))
            storage.addAttribute(.underlineStyle, value: NSUnderlineStyle.single.rawValue, range: m.range(at: 1))
        }
    }

    private static func each(_ re: NSRegularExpression, _ ns: NSString, _ range: NSRange, _ body: (NSTextCheckingResult) -> Void) {
        re.enumerateMatches(in: ns as String, range: range) { m, _, _ in if let m { body(m) } }
    }

    /// Dim the `n` leading + `n` trailing marker chars of a wrapped span.
    private static func dimEdges(_ storage: NSTextStorage, _ range: NSRange, _ n: Int, _ dim: NSColor) {
        storage.addAttribute(.foregroundColor, value: dim, range: NSRange(location: range.location, length: n))
        storage.addAttribute(.foregroundColor, value: dim, range: NSRange(location: range.location + range.length - n, length: n))
    }
}
