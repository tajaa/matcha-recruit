import SwiftUI

/// Create-journal sheet. Color + icon stay constrained to a small picker
/// so the backend `color VARCHAR(20)` / `icon VARCHAR(64)` columns don't
/// drift to free-form values across clients.
struct NewJournalSheet: View {
    let onCreated: (MWJournal) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var description = ""
    @State private var color: String = "matcha"
    @State private var icon: String = "book"
    @State private var creating = false
    @State private var error: String?

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

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("New Journal")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Spacer()
                Button("Close") { dismiss() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            .padding(14)

            Divider().opacity(0.3)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    field(label: "Title") {
                        TextField("", text: $title, prompt: Text("Marketing ideas").foregroundColor(.white.opacity(0.25)))
                            .textFieldStyle(.plain)
                            .font(.system(size: 13))
                            .foregroundColor(.white)
                    }

                    field(label: "Description (optional)") {
                        TextField("", text: $description, prompt: Text("What this journal is about").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                            .lineLimit(1...3)
                    }

                    field(label: "Color") {
                        HStack(spacing: 8) {
                            ForEach(colorOptions, id: \.0) { name, swatch in
                                Circle()
                                    .fill(swatch)
                                    .frame(width: 22, height: 22)
                                    .overlay(
                                        Circle().stroke(Color.white, lineWidth: color == name ? 2 : 0)
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
                                    .foregroundColor(icon == sym ? Color.matcha500 : .white.opacity(0.6))
                                    .frame(width: 30, height: 30)
                                    .background(
                                        RoundedRectangle(cornerRadius: 5)
                                            .fill(icon == sym ? Color.white.opacity(0.08) : Color.zinc800.opacity(0.5))
                                    )
                                    .onTapGesture { icon = sym }
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
                .tint(Color.matcha600)
                .controlSize(.small)
                .disabled(creating || title.trimmingCharacters(in: .whitespaces).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(12)
        }
        .frame(width: 420, height: 500)
        .background(Color.appBackground)
    }

    private func field<Content: View>(label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
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
