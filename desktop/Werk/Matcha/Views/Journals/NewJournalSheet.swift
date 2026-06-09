import SwiftUI

/// Create-journal sheet. The Type picker chooses a create-time template
/// (note/blog/todo/novel/screenplay) that seeds a starter entry on the backend
/// and sets a default icon. Color + icon stay constrained to small pickers so
/// the backend `color VARCHAR(20)` / `icon VARCHAR(64)` columns don't drift to
/// free-form values across clients.
struct NewJournalSheet: View {
    /// Folder to file the new journal into (passed by the Journals hub when a
    /// folder is selected). nil = hub root.
    var initialFolderId: String? = nil
    let onCreated: (MWJournal) -> Void

    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    @State private var title = ""
    @State private var description = ""
    @State private var kind: JournalKind = .note
    @State private var color: String = "matcha"
    @State private var icon: String = "note.text"
    @State private var iconTouched = false
    @State private var creating = false
    @State private var error: String?
    @FocusState private var titleFocused: Bool

    private let colorOptions: [(String, Color)] = [
        ("matcha", Color.matcha500),
        ("amber", .orange),
        ("blue", .blue),
        ("purple", .purple),
        ("pink", .pink),
    ]
    private let iconOptions = [
        "book", "book.closed", "lightbulb", "leaf",
        "scroll", "doc.text", "text.book.closed", "sparkles",
    ]
    private let kindColumns = [GridItem(.adaptive(minimum: 104, maximum: 160), spacing: 8)]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("New Journal")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
                Button("Close") { dismiss() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .padding(14)

            Divider().opacity(0.3)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    field(label: "Type") {
                        VStack(alignment: .leading, spacing: 8) {
                            LazyVGrid(columns: kindColumns, spacing: 8) {
                                ForEach(JournalKind.allCases) { k in
                                    kindChip(k)
                                }
                            }
                            Text(kind.blurb)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeTextSecondary)
                        }
                    }

                    field(label: "Title") {
                        HStack(spacing: 6) {
                            TextField("", text: $title, prompt: Text("Marketing ideas").foregroundColor(appState.themeTextSecondary.opacity(0.6)))
                                .textFieldStyle(.plain)
                                .font(.system(size: 13))
                                .foregroundColor(appState.themeText)
                                .focused($titleFocused)
                            EmojiPaletteButton { titleFocused = true }
                        }
                    }

                    field(label: "Description (optional)") {
                        TextField("", text: $description, prompt: Text("What this journal is about").foregroundColor(appState.themeTextSecondary.opacity(0.6)), axis: .vertical)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText)
                            .lineLimit(1...3)
                    }

                    field(label: "Color") {
                        HStack(spacing: 8) {
                            ForEach(colorOptions, id: \.0) { name, swatch in
                                Circle()
                                    .fill(swatch)
                                    .frame(width: 22, height: 22)
                                    .overlay(
                                        Circle().stroke(appState.themeText, lineWidth: color == name ? 2 : 0)
                                    )
                                    .onTapGesture { color = name }
                            }
                        }
                    }

                    field(label: "Icon") {
                        LazyVGrid(columns: Array(repeating: GridItem(.fixed(34), spacing: 6), count: 8), spacing: 6) {
                            ForEach(iconOptions, id: \.self) { sym in
                                Image(systemName: sym)
                                    .font(.system(size: 14))
                                    .foregroundColor(icon == sym ? appState.themeAccent : appState.themeText.opacity(0.6))
                                    .frame(width: 30, height: 30)
                                    .background(
                                        RoundedRectangle(cornerRadius: 5)
                                            .fill(icon == sym ? appState.themeAccent.opacity(0.12) : appState.themeCard.opacity(0.5))
                                    )
                                    .onTapGesture { icon = sym; iconTouched = true }
                            }
                        }
                    }

                    if let error {
                        Text(error)
                            .font(.system(size: 11))
                            .foregroundColor(.red.opacity(0.85))
                    }
                }
                .padding(14)
            }

            Divider().opacity(0.3)

            HStack {
                Spacer()
                Button {
                    Task { await create() }
                } label: {
                    if creating {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Create").font(.system(size: 12, weight: .semibold))
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .controlSize(.small)
                .disabled(creating || title.trimmingCharacters(in: .whitespaces).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(12)
        }
        .frame(width: 440, height: 560)
        .background(appState.themeBg)
    }

    /// Lite+ journal kinds — basic note/todo/journal stay free. Mirrors the
    /// server's PREMIUM_JOURNAL_KINDS gate on POST /journals.
    private func isPremiumKind(_ k: JournalKind) -> Bool {
        ["novel", "screenplay", "blog"].contains(k.rawValue)
    }

    private func kindChip(_ k: JournalKind) -> some View {
        let selected = kind == k
        let locked = isPremiumKind(k) && !appState.canFullJournals
        return Button {
            if locked {
                appState.presentPaywall(for: "journals_full")
                return
            }
            kind = k
            // Default the icon to the type's icon until the user overrides it.
            if !iconTouched { icon = k.icon }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: locked ? "lock.fill" : k.icon).font(.system(size: 12))
                Text(k.label).font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .foregroundColor(selected ? appState.themeOnAccent : appState.themeText.opacity(locked ? 0.5 : 1))
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 7)
                    .fill(selected ? appState.themeAccent : appState.themeCard.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(appState.themeBorder, lineWidth: selected ? 0 : 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(locked ? "This journal type needs Werk Lite" : "")
    }

    private func field<Content: View>(label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
            content()
            Divider()
        }
    }

    private func create() async {
        creating = true
        error = nil
        defer { creating = false }
        let trimmed = title.trimmingCharacters(in: .whitespaces)
        do {
            let journal = try await MatchaWorkService.shared.createJournal(
                title: trimmed,
                description: description.isEmpty ? nil : description,
                color: color,
                icon: icon,
                kind: kind.rawValue,
                folderId: initialFolderId,
            )
            onCreated(journal)
            dismiss()
        } catch let apiError as APIError {
            // 404 here means the journals routes aren't registered on the
            // backend the client is talking to — almost always a stale
            // deploy. Surface a friendly hint instead of the raw FastAPI
            // `{"detail":"Not Found"}` body.
            if case .httpError(let code, _) = apiError, code == 404 {
                self.error = "Couldn't create journal. The server may need to be updated — try again in a moment or contact support."
            } else {
                self.error = apiError.localizedDescription
            }
            print("[NewJournalSheet] create failed: \(apiError)")
        } catch {
            self.error = error.localizedDescription
        }
    }
}
