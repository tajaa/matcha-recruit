import AppKit
import Foundation

/// Markdown list behaviour for an `NSTextView`: Return continues the list,
/// Tab / Shift-Tab nest and un-nest it (renumbering ordered items into the
/// depth's outline style).
///
/// Split out of `RichJournalEditor.Coordinator`, which mixed this pure text
/// manipulation in with SwiftUI plumbing and slash-menu panel management. It is
/// stateless — the caller owns the "push the new string into the binding and
/// re-style" step, which is the only part that isn't about text.
///
/// The regexes are compiled once as statics. They previously went through a
/// `try? NSRegularExpression(pattern:)` helper that recompiled every pattern on
/// every keystroke, since `handleReturn` runs from the Return key path.
enum MarkdownListEditing {

    /// What a key press did, so the caller knows whether to sync its binding.
    enum Outcome {
        /// Not a list context — let NSTextView apply its default behaviour.
        case notHandled
        /// Consumed the key, but the text is unchanged.
        case handled
        /// Consumed the key AND mutated the text: push `tv.string` into the
        /// binding and re-run the markdown styler.
        case edited
    }

    // MARK: - Patterns

    private static func rx(_ p: String) -> NSRegularExpression {
        // Patterns are constant + valid; `try!` is fine and compiles once.
        try! NSRegularExpression(pattern: p)
    }

    /// Continuation forms — the trailing group is the line's content, empty on
    /// an item the user is about to close out.
    private static let reContinueTodo    = rx(#"^([ \t]*)([-*])[ \t]+\[[ xX]\][ \t]+(.*)$"#)
    private static let reContinueOrdered = rx(#"^([ \t]*)([0-9A-Za-z]+)\.[ \t]+(.*)$"#)
    private static let reContinueBullet  = rx(#"^([ \t]*)([-*])[ \t]+(.*)$"#)
    private static let reContinueQuote   = rx(#"^([ \t]*)>[ \t]+(.*)$"#)
    /// Parse forms — the bullet one excludes checkboxes so `.todo` wins.
    private static let reParseTodo   = rx(#"^([ \t]*)([-*])[ \t]+\[([ xX])\][ \t]+(.*)$"#)
    private static let reParseBullet = rx(#"^([ \t]*)([-*])[ \t]+(?!\[[ xX]\])(.*)$"#)

    // MARK: - Line model

    enum ListKind { case ordered, bullet, todo }

    struct ListLine {
        let indent: String
        let kind: ListKind
        let bullet: String
        let checked: Bool
        let content: String
    }

    // MARK: - Return: continue or end the list

    /// On Return inside a list/quote line, continue the list (next bullet /
    /// number / checkbox / quote). On an *empty* item, end the list by
    /// clearing the marker.
    static func handleReturn(_ tv: NSTextView) -> Outcome {
        let ns = tv.string as NSString
        let sel = tv.selectedRange()
        guard sel.length == 0 else { return .notHandled }
        let lineRange = ns.lineRange(for: NSRange(location: sel.location, length: 0))
        let head = ns.substring(with: NSRange(location: lineRange.location, length: sel.location - lineRange.location))

        // To-do (check before bullet — it starts with the same `-`/`*`).
        if let m = match(reContinueTodo, head) {
            let indent = group(m, 1, head), bullet = group(m, 2, head)
            if group(m, 3, head).isEmpty { return exitList(tv, lineRange.location, sel.location) }
            return continueList(tv, sel.location, "\n\(indent)\(bullet) [ ] ")
        }
        // Ordered — decimal at depth 0, alpha/roman when indented (outline).
        if let m = match(reContinueOrdered, head) {
            let indent = group(m, 1, head)
            let marker = group(m, 2, head)
            let depth = indentWidth(indent) / 4
            // At depth 0 require real digits so prose like "etc. " isn't a list.
            if depth > 0 || marker.allSatisfy(\.isNumber) {
                if group(m, 3, head).isEmpty { return exitList(tv, lineRange.location, sel.location) }
                let next = orderedMarker(depth, orderedIndex(marker, depth) + 1)
                return continueList(tv, sel.location, "\n\(indent)\(next). ")
            }
        }
        // Bullet.
        if let m = match(reContinueBullet, head) {
            let indent = group(m, 1, head), bullet = group(m, 2, head)
            if group(m, 3, head).isEmpty { return exitList(tv, lineRange.location, sel.location) }
            return continueList(tv, sel.location, "\n\(indent)\(bullet) ")
        }
        // Blockquote.
        if let m = match(reContinueQuote, head) {
            let indent = group(m, 1, head)
            if group(m, 2, head).isEmpty { return exitList(tv, lineRange.location, sel.location) }
            return continueList(tv, sel.location, "\n\(indent)> ")
        }
        return .notHandled
    }

    /// Insert the continuation marker at the caret.
    private static func continueList(_ tv: NSTextView, _ caret: Int, _ str: String) -> Outcome {
        let r = NSRange(location: caret, length: 0)
        guard tv.shouldChangeText(in: r, replacementString: str) else { return .handled }
        tv.textStorage?.replaceCharacters(in: r, with: str)
        tv.didChangeText()
        tv.setSelectedRange(NSRange(location: caret + (str as NSString).length, length: 0))
        return .edited
    }

    /// Empty item + Return → clear the marker, leaving a blank line.
    private static func exitList(_ tv: NSTextView, _ lineStart: Int, _ caret: Int) -> Outcome {
        let r = NSRange(location: lineStart, length: caret - lineStart)
        guard tv.shouldChangeText(in: r, replacementString: "") else { return .handled }
        tv.textStorage?.replaceCharacters(in: r, with: "")
        tv.didChangeText()
        return .edited
    }

    // MARK: - Tab / Shift-Tab: outline nesting

    /// Tab / Shift-Tab on a list line: indent or outdent one level. Ordered
    /// items renumber to the new depth's outline style (continuing siblings);
    /// bullets/todos just shift indent. Returns `.notHandled` on a non-list
    /// line so Tab keeps its default behavior.
    static func handleIndent(_ tv: NSTextView, demote: Bool) -> Outcome {
        let ns = tv.string as NSString
        let sel = tv.selectedRange()
        let lineRange = ns.lineRange(for: NSRange(location: sel.location, length: 0))
        var len = lineRange.length
        if len > 0, ns.substring(with: NSRange(location: lineRange.location + len - 1, length: 1)) == "\n" { len -= 1 }
        let lineNoNL = NSRange(location: lineRange.location, length: len)
        let line = ns.substring(with: lineNoNL)
        guard let info = parseListLine(line) else { return .notHandled }

        let oldDepth = indentWidth(info.indent) / 4
        if !demote && oldDepth == 0 { return .handled }        // already top level — swallow Shift-Tab
        let newDepth = demote ? oldDepth + 1 : oldDepth - 1
        let newIndent = String(repeating: " ", count: newDepth * 4)

        let newLine: String
        switch info.kind {
        case .ordered:
            let lines = ns.components(separatedBy: "\n")
            let lineIdx = ns.substring(to: lineRange.location).components(separatedBy: "\n").count - 1
            let idx = siblingIndex(lines: lines, lineIdx: lineIdx, depth: newDepth)
            newLine = "\(newIndent)\(orderedMarker(newDepth, idx)). \(info.content)"
        case .bullet:
            newLine = "\(newIndent)\(info.bullet) \(info.content)"
        case .todo:
            newLine = "\(newIndent)\(info.bullet) [\(info.checked ? "x" : " ")] \(info.content)"
        }

        guard tv.shouldChangeText(in: lineNoNL, replacementString: newLine) else { return .handled }
        tv.textStorage?.replaceCharacters(in: lineNoNL, with: newLine)
        tv.didChangeText()
        let delta = (newLine as NSString).length - lineNoNL.length
        let caret = min(max(sel.location + delta, lineRange.location), lineRange.location + (newLine as NSString).length)
        tv.setSelectedRange(NSRange(location: caret, length: 0))
        return .edited
    }

    // MARK: - Parsing

    static func parseListLine(_ line: String) -> ListLine? {
        if let m = match(reParseTodo, line) {
            return ListLine(indent: group(m, 1, line), kind: .todo, bullet: group(m, 2, line),
                            checked: group(m, 3, line).lowercased() == "x", content: group(m, 4, line))
        }
        if let m = match(reParseBullet, line) {
            return ListLine(indent: group(m, 1, line), kind: .bullet, bullet: group(m, 2, line),
                            checked: false, content: group(m, 3, line))
        }
        if let m = match(reContinueOrdered, line) {
            let indent = group(m, 1, line), marker = group(m, 2, line)
            if indentWidth(indent) / 4 > 0 || marker.allSatisfy(\.isNumber) {
                return ListLine(indent: indent, kind: .ordered, bullet: marker, checked: false, content: group(m, 3, line))
            }
        }
        return nil
    }

    private static func match(_ re: NSRegularExpression, _ s: String) -> NSTextCheckingResult? {
        re.firstMatch(in: s, range: NSRange(location: 0, length: (s as NSString).length))
    }

    private static func group(_ m: NSTextCheckingResult, _ i: Int, _ s: String) -> String {
        let r = m.range(at: i)
        return r.location == NSNotFound ? "" : (s as NSString).substring(with: r)
    }

    /// 4 columns per indent level (a tab counts as a full level).
    static func indentWidth(_ s: String) -> Int {
        var w = 0
        for c in s { if c == "\t" { w += 4 } else if c == " " { w += 1 } else { break } }
        return w
    }

    /// Count preceding ordered siblings at `depth` (stopping at a shallower
    /// line or a gap) to give the renumbered item its correct outline index.
    private static func siblingIndex(lines: [String], lineIdx: Int, depth: Int) -> Int {
        var count = 0, i = lineIdx - 1
        while i >= 0 {
            let l = lines[i]
            if l.trimmingCharacters(in: .whitespaces).isEmpty { break }
            let d = indentWidth(l) / 4
            if d < depth { break }
            if d == depth {
                if parseListLine(l)?.kind == .ordered { count += 1 } else { break }
            }
            i -= 1
        }
        return count + 1
    }

    // MARK: - Outline numerals

    /// Outline marker for an ordered item by depth: 0 → 1. , 1 → a. , 2 → i. ,
    /// then the cycle repeats (decimal / lower-alpha / lower-roman).
    static func orderedMarker(_ depth: Int, _ index: Int) -> String {
        switch ((depth % 3) + 3) % 3 {
        case 1:  return intToAlpha(index)
        case 2:  return intToRoman(index)
        default: return String(index)
        }
    }

    /// Parse an existing marker back to its 1-based index, per the depth's style.
    static func orderedIndex(_ marker: String, _ depth: Int) -> Int {
        switch ((depth % 3) + 3) % 3 {
        case 1:  return alphaToInt(marker)
        case 2:  return romanToInt(marker)
        default: return Int(marker) ?? 1
        }
    }

    static func intToAlpha(_ n: Int) -> String {
        var n = max(1, n), s = ""
        while n > 0 { let r = (n - 1) % 26; s = String(UnicodeScalar(97 + r)!) + s; n = (n - 1) / 26 }
        return s
    }

    static func alphaToInt(_ s: String) -> Int {
        var n = 0
        for u in s.lowercased().unicodeScalars {
            guard u.value >= 97, u.value <= 122 else { break }
            n = n * 26 + Int(u.value - 96)
        }
        return max(1, n)
    }

    static func intToRoman(_ n: Int) -> String {
        let table: [(Int, String)] = [(1000,"m"),(900,"cm"),(500,"d"),(400,"cd"),(100,"c"),(90,"xc"),(50,"l"),(40,"xl"),(10,"x"),(9,"ix"),(5,"v"),(4,"iv"),(1,"i")]
        var n = max(1, n), s = ""
        for (v, sym) in table { while n >= v { s += sym; n -= v } }
        return s
    }

    static func romanToInt(_ s: String) -> Int {
        let map: [Character: Int] = ["i":1,"v":5,"x":10,"l":50,"c":100,"d":500,"m":1000]
        let chars = Array(s.lowercased()); var total = 0
        for (i, ch) in chars.enumerated() {
            guard let v = map[ch] else { return 1 }
            if i + 1 < chars.count, let nv = map[chars[i + 1]], v < nv { total -= v } else { total += v }
        }
        return max(1, total)
    }
}
