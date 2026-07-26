import SwiftUI

/// Start a new 1:1 direct message: search people, pick one, write the first
/// message. Calls back so the list can refresh on success.
struct NewConversationView: View {
    var onCreated: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var results: [MWInboxUserSearch] = []
    @State private var selected: MWInboxUserSearch?
    @State private var message = ""
    @State private var isCreating = false
    @State private var errorMessage: String?

    private let service = InboxService.shared

    var body: some View {
        NavigationStack {
            Group {
                if let person = selected {
                    composer(person)
                } else {
                    searchList
                }
            }
            .navigationTitle(selected == nil ? "New Message" : "Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                if selected != nil {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Back") { selected = nil }
                    }
                }
            }
        }
    }

    private var searchList: some View {
        List {
            ForEach(results) { person in
                Button { selected = person } label: {
                    HStack(spacing: 12) {
                        Avatar(url: person.avatarUrl, name: person.name, size: 40)
                        VStack(alignment: .leading) {
                            Text(person.name).foregroundStyle(.primary)
                            Text(person.email).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if results.isEmpty, !query.isEmpty {
                Text("No people found").foregroundStyle(.secondary)
            }
        }
        .listStyle(.plain)
        .searchable(text: $query, prompt: "Search people")
        .task(id: query) { await search() }
    }

    private func composer(_ person: MWInboxUserSearch) -> some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Avatar(url: person.avatarUrl, name: person.name, size: 44)
                VStack(alignment: .leading) {
                    Text(person.name).font(.headline)
                    Text(person.email).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding()

            TextField("Write a message…", text: $message, axis: .vertical)
                .lineLimit(3...8)
                .textFieldStyle(.roundedBorder)
                .padding(.horizontal)

            if let err = errorMessage {
                Text(err).font(.footnote).foregroundStyle(.red)
            }

            Button(action: create) {
                if isCreating { ProgressView().frame(maxWidth: .infinity) }
                else { Text("Send").frame(maxWidth: .infinity) }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal)
            .disabled(message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isCreating)

            Spacer()
        }
    }

    private func search() async {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else { results = []; return }
        try? await Task.sleep(for: .milliseconds(250))   // debounce
        guard !Task.isCancelled else { return }
        results = (try? await service.searchUsers(query: q)) ?? []
    }

    private func create() {
        let body = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let person = selected, !body.isEmpty, !isCreating else { return }
        isCreating = true
        Task {
            do {
                _ = try await service.createConversation(participantIds: [person.id], message: body)
                await onCreated()
                await MainActor.run { dismiss() }
            } catch {
                await MainActor.run {
                    isCreating = false
                    errorMessage = error.localizedDescription
                }
            }
        }
    }
}
