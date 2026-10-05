import SwiftUI

struct NewConversationView: View {
    @Environment(\.dismiss) private var dismiss
    let onCreated: (String) async -> Void
    @State private var query = ""
    @State private var results: [MWInboxUserSearch] = []
    @State private var selected: MWInboxUserSearch?
    @State private var draft = ""
    @State private var creating = false
    @State private var searching = false
    @State private var error: String?
    @FocusState private var draftFocused: Bool

    var body: some View {
        NavigationStack {
            Group {
                if let selected {
                    compose(to: selected)
                } else {
                    search
                }
            }
            .navigationTitle(selected == nil ? "New message" : "Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Cancel") { dismiss() }
                }
                if selected != nil {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { selected = nil } label: { Image(systemName: "chevron.left") }
                            .accessibilityLabel("Back to people")
                    }
                }
            }
        }
    }

    private var search: some View {
        List {
            if let error {
                Section { ErrorRow(message: error) }
            }
            ForEach(results) { person in
                Button { selected = person; draftFocused = true } label: {
                    HStack(spacing: 12) {
                        Avatar(name: person.name, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(person.name).foregroundStyle(Color.primary)
                            Text(person.email).font(.caption).foregroundStyle(Color.secondary)
                        }
                    }
                }
            }
        }
        .overlay {
            if searching && results.isEmpty {
                ProgressView()
            } else if results.isEmpty && error == nil {
                if query.trimmingCharacters(in: .whitespaces).count >= 2 {
                    ContentUnavailableView.search(text: query)
                } else {
                    ContentUnavailableView("Find a coworker", systemImage: "magnifyingglass",
                                           description: Text("Type at least two letters of a name."))
                }
            }
        }
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                    prompt: "Search coworkers by name or email")
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .task(id: query) { await runSearch() }
    }

    private func compose(to person: MWInboxUserSearch) -> some View {
        Form {
            Section("To") {
                HStack(spacing: 12) {
                    Avatar(name: person.name, size: 36)
                    Text(person.name)
                }
            }
            Section {
                TextField("Write a message", text: $draft, axis: .vertical)
                    .lineLimit(4...10)
                    .focused($draftFocused)
            }
            if let error {
                Section { ErrorRow(message: error) }
            }
            Section {
                Button { Task { await create(with: person) } } label: {
                    LoadingLabel(title: "Send", busy: creating)
                }
                .primaryActionRow()
                .disabled(creating || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
    }

    private func runSearch() async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 2 else { results = []; return }
        do { try await Task.sleep(for: .milliseconds(250)) }
        catch { return }
        guard !Task.isCancelled else { return }
        searching = true
        defer { searching = false }
        do {
            results = try await InboxService.shared.searchUsers(trimmed)
            error = nil
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
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
