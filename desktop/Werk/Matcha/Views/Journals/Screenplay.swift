import Foundation

// MARK: - Screenplay element model

/// The element types a screenplay line can be. These map 1:1 to the standard
/// Final Draft / Fountain element styles and drive both the on-screen editor
/// formatting and the paginated PDF layout.
enum ScreenplayElement: String, Codable, CaseIterable, Hashable {
    case sceneHeading      // INT. COFFEE SHOP - DAY
    case action            // Description / stage direction.
    case character         // FINCH
    case parenthetical     // (beat)
    case dialogue          // Their line.
    case transition        // CUT TO:
    case shot              // ANGLE ON, CLOSE ON …
    case centered          // > centered text <
    case section           // # Act One   (organizational, not printed)
    case synopsis          // = a one-line synopsis  (organizational)
    case pageBreak         // ===

    var displayName: String {
        switch self {
        case .sceneHeading:  return "Scene Heading"
        case .action:        return "Action"
        case .character:     return "Character"
        case .parenthetical: return "Parenthetical"
        case .dialogue:      return "Dialogue"
        case .transition:    return "Transition"
        case .shot:          return "Shot"
        case .centered:      return "Centered"
        case .section:       return "Section"
        case .synopsis:      return "Synopsis"
        case .pageBreak:     return "Page Break"
        }
    }

    /// Whether this element is rendered UPPERCASE in standard format.
    var isUppercased: Bool {
        switch self {
        case .sceneHeading, .character, .transition, .shot: return true
        default: return false
        }
    }

    /// The element a fresh Return creates after this one (Final Draft's smart
    /// auto-advance). Tab cycling uses a different order (see `tabCycle`).
    var afterReturn: ScreenplayElement {
        switch self {
        case .sceneHeading:  return .action
        case .action:        return .action
        case .character:     return .dialogue
        case .parenthetical: return .dialogue
        case .dialogue:      return .action
        case .transition:    return .sceneHeading
        case .shot:          return .action
        case .centered:      return .action
        case .section:       return .action
        case .synopsis:      return .action
        case .pageBreak:     return .sceneHeading
        }
    }

    /// Tab cycles through the most common writing elements in place.
    var tabCycle: ScreenplayElement {
        switch self {
        case .action:        return .character
        case .character:     return .sceneHeading
        case .sceneHeading:  return .transition
        case .transition:    return .action
        case .dialogue:      return .parenthetical
        case .parenthetical: return .dialogue
        default:             return .action
        }
    }
}

/// One line of a screenplay. The editor and paginator both operate on arrays of
/// these. `dual` marks the right column of a dual (simultaneous) dialogue pair.
struct ScreenplayLine: Identifiable, Hashable {
    var id = UUID()
    var element: ScreenplayElement
    var text: String
    var dual: Bool = false
    var sceneNumber: String? = nil
}

/// Fountain title-page fields (the standard subset). Rendered as page 1 of the
/// exported PDF and round-tripped through the `Key: value` block at the top of
/// the Fountain source.
struct ScreenplayTitlePage: Hashable {
    var title: String = ""
    var credit: String = "Written by"
    var author: String = ""
    var source: String = ""
    var draftDate: String = ""
    var contact: String = ""

    var isEmpty: Bool {
        [title, author, source, draftDate, contact].allSatisfy { $0.isEmpty }
            && (credit.isEmpty || credit == "Written by")
    }
}

/// A parsed screenplay: an optional title page plus the ordered body lines.
struct ScreenplayDocument: Hashable {
    var titlePage = ScreenplayTitlePage()
    var lines: [ScreenplayLine] = []
}

// MARK: - Fountain parse / serialize

/// A focused, dependency-free Fountain reader/writer. Covers the elements the
/// editor produces: title page, scene headings, action, character, dialogue,
/// parentheticals, transitions, centered text, sections, synopses, dual
/// dialogue (`^`), forced syntax (`.`/`@`/`!`/`>`), and page breaks (`===`).
/// Round-trips stably so autosave never mutates a script.
enum FountainParser {

    // MARK: Parse

    static func parse(_ text: String) -> ScreenplayDocument {
        var doc = ScreenplayDocument()
        let all = text.components(separatedBy: "\n")
        var i = 0

        // Title page: only when the very first non-empty line is a "Key:" line.
        if let first = all.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty }),
           titlePageKey(first) != nil {
            i = parseTitlePage(all, into: &doc.titlePage)
        }

        var prevBlank = true
        var inDialogue = false
        var lastWasDual = false

        while i < all.count {
            let line = all[i].trimmingCharacters(in: .whitespaces)

            if line.isEmpty { prevBlank = true; inDialogue = false; lastWasDual = false; i += 1; continue }

            // Page break.
            if line.allSatisfy({ $0 == "=" }) && line.count >= 3 {
                doc.lines.append(ScreenplayLine(element: .pageBreak, text: ""))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Section (# …) / synopsis (= …).
            if let s = stripPrefix(line, "#") { doc.lines.append(ScreenplayLine(element: .section, text: s)); prevBlank = false; inDialogue = false; i += 1; continue }
            if line.hasPrefix("= ") { doc.lines.append(ScreenplayLine(element: .synopsis, text: String(line.dropFirst(2)))); prevBlank = false; i += 1; continue }
            // Centered: > text <
            if line.hasPrefix(">"), line.hasSuffix("<") {
                let inner = line.dropFirst().dropLast().trimmingCharacters(in: .whitespaces)
                doc.lines.append(ScreenplayLine(element: .centered, text: String(inner)))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Forced transition: > text
            if line.hasPrefix(">") {
                doc.lines.append(ScreenplayLine(element: .transition, text: String(line.dropFirst()).trimmingCharacters(in: .whitespaces)))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Forced scene heading: .text  (but not "..")
            if line.hasPrefix("."), !line.hasPrefix("..") {
                doc.lines.append(ScreenplayLine(element: .sceneHeading, text: String(line.dropFirst())))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Forced action: !text
            if line.hasPrefix("!") {
                doc.lines.append(ScreenplayLine(element: .action, text: String(line.dropFirst())))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Forced character: @NAME
            if line.hasPrefix("@") {
                let (name, dual) = stripDual(String(line.dropFirst()))
                doc.lines.append(ScreenplayLine(element: .character, text: name, dual: dual))
                prevBlank = false; inDialogue = true; lastWasDual = dual; i += 1; continue
            }
            // Scene heading by prefix.
            if isSceneHeading(line) {
                doc.lines.append(ScreenplayLine(element: .sceneHeading, text: line))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Transition by all-caps + "TO:".
            if prevBlank, isTransition(line) {
                doc.lines.append(ScreenplayLine(element: .transition, text: line))
                prevBlank = false; inDialogue = false; i += 1; continue
            }
            // Parenthetical inside a dialogue block.
            if inDialogue, line.hasPrefix("("), line.hasSuffix(")") {
                doc.lines.append(ScreenplayLine(element: .parenthetical, text: line, dual: lastWasDual))
                prevBlank = false; i += 1; continue
            }
            // Character cue: blank-preceded, all-caps, followed by dialogue.
            let next = (i + 1 < all.count) ? all[i + 1] : ""
            if prevBlank, isCharacter(line, next: next) {
                let (name, dual) = stripDual(line)
                doc.lines.append(ScreenplayLine(element: .character, text: name, dual: dual))
                prevBlank = false; inDialogue = true; lastWasDual = dual; i += 1; continue
            }
            // Dialogue continuation.
            if inDialogue {
                doc.lines.append(ScreenplayLine(element: .dialogue, text: line, dual: lastWasDual))
                prevBlank = false; i += 1; continue
            }
            // Default: action.
            doc.lines.append(ScreenplayLine(element: .action, text: line))
            prevBlank = false; inDialogue = false; i += 1
        }
        return doc
    }

    // MARK: Serialize

    static func serialize(_ doc: ScreenplayDocument) -> String {
        var out = ""
        let tp = doc.titlePage
        if !tp.isEmpty {
            if !tp.title.isEmpty     { out += "Title: \(tp.title)\n" }
            if !tp.credit.isEmpty    { out += "Credit: \(tp.credit)\n" }
            if !tp.author.isEmpty    { out += "Author: \(tp.author)\n" }
            if !tp.source.isEmpty    { out += "Source: \(tp.source)\n" }
            if !tp.draftDate.isEmpty { out += "Draft date: \(tp.draftDate)\n" }
            if !tp.contact.isEmpty   { out += "Contact: \(tp.contact)\n" }
            out += "\n"
        }
        var prev: ScreenplayElement? = nil
        for line in doc.lines {
            let blankBefore: Bool
            switch line.element {
            case .dialogue, .parenthetical: blankBefore = false
            default: blankBefore = true
            }
            if prev != nil, blankBefore { out += "\n" }
            switch line.element {
            case .sceneHeading:
                out += (isSceneHeading(line.text) ? line.text : ".\(line.text)") + "\n"
            case .action:
                // Force with "!" if the action would otherwise be misread as a cue/heading.
                let ambiguous = isSceneHeading(line.text) || isTransition(line.text)
                    || (line.text == line.text.uppercased() && line.text.contains { $0.isLetter })
                out += (ambiguous ? "!\(line.text)" : line.text) + "\n"
            case .character:
                out += line.text + (line.dual ? " ^" : "") + "\n"
            case .parenthetical:
                out += line.text + "\n"
            case .dialogue:
                out += line.text + "\n"
            case .transition:
                out += (isTransition(line.text) ? line.text : "> \(line.text)") + "\n"
            case .shot:
                out += line.text + "\n"
            case .centered:
                out += "> \(line.text) <\n"
            case .section:
                out += "# \(line.text)\n"
            case .synopsis:
                out += "= \(line.text)\n"
            case .pageBreak:
                out += "===\n"
            }
            prev = line.element
        }
        return out
    }

    // MARK: Helpers

    static func isSceneHeading(_ s: String) -> Bool {
        let u = s.uppercased()
        return u.hasPrefix("INT.") || u.hasPrefix("EXT.") || u.hasPrefix("EST.")
            || u.hasPrefix("INT/EXT") || u.hasPrefix("INT./EXT") || u.hasPrefix("I/E ")
            || u.hasPrefix("INT ") || u.hasPrefix("EXT ")
    }

    static func isTransition(_ s: String) -> Bool {
        guard !s.isEmpty, s == s.uppercased(), s.contains(where: { $0.isLetter }) else { return false }
        if s.hasSuffix("TO:") { return true }
        return ["FADE OUT.", "FADE TO BLACK.", "FADE IN:", "CUT TO BLACK."].contains(s)
    }

    /// All-caps name (allowing a trailing `(V.O.)`-style extension and `^` dual
    /// marker), preceded by a blank line and followed by non-blank dialogue.
    static func isCharacter(_ s: String, next: String) -> Bool {
        guard !next.trimmingCharacters(in: .whitespaces).isEmpty else { return false }
        let core = stripDual(s).0
        let nameOnly = core.replacingOccurrences(of: #"\([^)]*\)"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        guard !nameOnly.isEmpty, nameOnly.contains(where: { $0.isLetter }) else { return false }
        // Scene headings are also all-caps — don't swallow them.
        guard !isSceneHeading(nameOnly) else { return false }
        return nameOnly == nameOnly.uppercased()
    }

    private static func stripDual(_ s: String) -> (String, Bool) {
        var t = s.trimmingCharacters(in: .whitespaces)
        if t.hasSuffix("^") {
            t = String(t.dropLast()).trimmingCharacters(in: .whitespaces)
            return (t, true)
        }
        return (t, false)
    }

    /// Strip a leading run of `#` (section heading) — returns nil if not one.
    private static func stripPrefix(_ s: String, _ ch: Character) -> String? {
        guard s.first == ch else { return nil }
        var rest = Substring(s)
        while rest.first == ch { rest = rest.dropFirst() }
        guard rest.first == " " else { return nil }
        return String(rest.dropFirst())
    }

    // MARK: Title page

    private static func titlePageKey(_ line: String) -> String? {
        guard let colon = line.firstIndex(of: ":") else { return nil }
        let key = line[..<colon].trimmingCharacters(in: .whitespaces)
        guard !key.isEmpty, key.allSatisfy({ $0.isLetter || $0 == " " }) else { return nil }
        return key
    }

    /// Parse the leading `Key: value` block; returns the index of the first body
    /// line (after the blank that terminates the title page).
    private static func parseTitlePage(_ all: [String], into tp: inout ScreenplayTitlePage) -> Int {
        var i = 0
        var lastKey: String? = nil
        while i < all.count {
            let raw = all[i]
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.isEmpty { i += 1; break }   // blank terminates the title page
            if let key = titlePageKey(line) {
                let colon = line.firstIndex(of: ":")!
                let value = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
                assign(key: key, value: value, into: &tp)
                lastKey = key
            } else if let lastKey, raw.first == " " || raw.first == "\t" {
                // Indented continuation line → append to the previous key.
                append(key: lastKey, value: line, into: &tp)
            }
            i += 1
        }
        return i
    }

    private static func assign(key: String, value: String, into tp: inout ScreenplayTitlePage) {
        switch key.lowercased() {
        case "title":                 tp.title = value
        case "credit":                tp.credit = value
        case "author", "authors":     tp.author = value
        case "source":                tp.source = value
        case "draft date", "date":    tp.draftDate = value
        case "contact":               tp.contact = value
        default: break
        }
    }

    private static func append(key: String, value: String, into tp: inout ScreenplayTitlePage) {
        let joined: (String) -> String = { $0.isEmpty ? value : $0 + "\n" + value }
        switch key.lowercased() {
        case "title":              tp.title = joined(tp.title)
        case "author", "authors":  tp.author = joined(tp.author)
        case "contact":            tp.contact = joined(tp.contact)
        default: break
        }
    }
}
