import SwiftUI

/// Per-journal style preferences popover. Lets the user pick font family,
/// size, and line spacing for both the editor and the rendered view.
/// Persistence is via `@AppStorage`, keyed by the journal id so each
/// journal can carry its own visual feel.
struct JournalStylePopover: View {
    let journalId: String

    // Storage keys live at the property level so SwiftUI can wire up the
    // bindings. We resolve them via journalId-prefixed strings.
    @AppStorage private var family: String
    @AppStorage private var size: Double
    @AppStorage private var spacing: Double

    init(journalId: String) {
        self.journalId = journalId
        _family = AppStorage(wrappedValue: "system", "journal.\(journalId).font.family")
        _size = AppStorage(wrappedValue: 13.0, "journal.\(journalId).font.size")
        _spacing = AppStorage(wrappedValue: 3.0, "journal.\(journalId).line.spacing")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Style")
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.white.opacity(0.6))
                .textCase(.uppercase)

            VStack(alignment: .leading, spacing: 4) {
                Text("Font").font(.system(size: 10)).foregroundColor(.secondary)
                Picker("", selection: $family) {
                    Text("System").tag("system")
                    Text("Serif").tag("serif")
                    Text("Mono").tag("monospaced")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Size").font(.system(size: 10)).foregroundColor(.secondary)
                    Spacer()
                    Text("\(Int(size))").font(.system(size: 10)).foregroundColor(.white.opacity(0.7))
                }
                Slider(value: $size, in: 11...20, step: 1)
                    .controlSize(.small)
            }

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Line spacing").font(.system(size: 10)).foregroundColor(.secondary)
                    Spacer()
                    Text("\(Int(spacing))").font(.system(size: 10)).foregroundColor(.white.opacity(0.7))
                }
                Slider(value: $spacing, in: 0...10, step: 1)
                    .controlSize(.small)
            }
        }
        .padding(12)
        .frame(width: 200)
    }
}

// MARK: - Reader helpers

/// Centralized accessors so views outside this file can read the same
/// values without re-typing the `@AppStorage` key strings.
enum JournalStyle {
    static func family(for journalId: String) -> String {
        UserDefaults.standard.string(forKey: "journal.\(journalId).font.family") ?? "system"
    }
    static func size(for journalId: String) -> CGFloat {
        let v = UserDefaults.standard.double(forKey: "journal.\(journalId).font.size")
        return v > 0 ? CGFloat(v) : 13
    }
    static func spacing(for journalId: String) -> CGFloat {
        let v = UserDefaults.standard.double(forKey: "journal.\(journalId).line.spacing")
        return v > 0 ? CGFloat(v) : 3
    }
}
