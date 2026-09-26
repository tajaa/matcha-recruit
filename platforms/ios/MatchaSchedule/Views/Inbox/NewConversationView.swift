import SwiftUI

struct NewConversationView: View {
    @Environment(\.dismiss) private var dismiss
    let onCreated: (String) async -> Void
    @State private var query = ""
    @State private var results: [MWInboxUserSearch] = []
    @State private var selected: MWInboxUserSearch?
    @State private var draft = ""
    @State private var creating = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Group {
                if let selected {
                    VStack(alignment: .leading, spacing: 16) {
                        Text("To: \(selected.name)").font(.headline)
                        TextField("Write a message…", text: $draft, axis: .vertical)
                            .lineLimit(3...8).textFieldStyle(.roundedBorder)
                        if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                        Button("Send") { Task { await create(with: selected) } }
                            .buttonStyle(.borderedProminent)
                            .disabled(creating || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        Spacer()
                    }
                    .padding()
                } else {
                    List(results) { person in
                        Button { selected = person } label: {
                            VStack(alignment: .leading) {
                                Text(person.name).foregroundStyle(.primary)
                                Text(person.email).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .searchable(text: $query, prompt: "Search people")
                    .task(id: query) { await search() }
                }
            }
            .navigationTitle(selected == nil ? "New message" : "Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button("Cancel") { dismiss() } }
                if selected != nil {
                    ToolbarItem(placement: .topBarLeading) { Button("Back") { selected = nil } }
                }
            }
        }
    }

    private func search() async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else { results = []; return }
        do { try await Task.sleep(for: .milliseconds(250)) }
        catch { return }
        guard !Task.isCancelled else { return }
        do { results = try await InboxService.shared.searchUsers(trimmed) }
        catch { self.error = error.localizedDescription }
    }

    private func create(with person: MWInboxUserSearch) async {
        creating = true
        defer { creating = false }
        do {
            let conversation = try await InboxService.shared.createConversation(
                with: person.id, message: draft.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            await onCreated(conversation.id)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
