import SwiftUI

struct FriendSearchView: View {
    @State private var query = ""
    @State private var results: [FriendSummary] = []
    @State private var suggestions: [FriendSummary] = []
    @State private var error: String?
    @State private var generation = 0

    var body: some View {
        List {
            Section {
                TextField("@handle or name", text: $query)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
            Section(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Suggestions" : "People") {
                ForEach(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? suggestions : results) { person in
                    FriendSearchRow(person: person) { refresh() }
                }
                if (query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? suggestions : results).isEmpty {
                    Text(query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "No suggestions yet." : "No people found.")
                        .foregroundStyle(TU.textDim)
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Find Friends")
        .task(id: query) {
            try? await Task.sleep(for: .milliseconds(450))
            guard !Task.isCancelled else { return }
            generation += 1
            let requestGeneration = generation
            let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
            do {
                if normalized.isEmpty {
                    suggestions = try await FriendsService.shared.suggestions()
                    guard requestGeneration == generation else { return }
                    results = []
                } else if normalized.count >= 2 {
                    results = try await FriendsService.shared.search(FriendHandle.normalize(normalized))
                    guard requestGeneration == generation else { return }
                    suggestions = []
                } else {
                    results = []
                }
            } catch {
                if !error.isCancellation { self.error = error.localizedDescription }
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: error).padding(.top, 8) }
    }

    private func refresh() {
        generation += 1
        Task { @MainActor in
            let normalized = query.trimmingCharacters(in: .whitespacesAndNewlines)
            if normalized.isEmpty {
                suggestions = (try? await FriendsService.shared.suggestions()) ?? []
            } else if normalized.count >= 2 {
                results = (try? await FriendsService.shared.search(FriendHandle.normalize(normalized))) ?? []
            }
        }
    }
}

private struct FriendSearchRow: View {
    let person: FriendSummary
    let onChanged: () -> Void
    @State private var isBusy = false

    var body: some View {
        HStack(spacing: 10) {
            NavigationLink { FriendProfileView(accountId: person.account_id) } label: {
                FriendRow(person: person)
            }
            action
        }
    }

    @ViewBuilder
    private var action: some View {
        switch person.status {
        case .none:
            Button("Add") { run { _ = try await FriendsService.shared.request(accountId: person.account_id) } }
        case .pending_in:
            Button("Accept") { run { _ = try await FriendsService.shared.accept(requestId: person.request_id ?? "") } }
        case .pending_out:
            Button("Cancel") { run { try await FriendsService.shared.cancel(requestId: person.request_id ?? "") } }
        case .friends:
            Text("Friends").font(.interCaption).foregroundStyle(TU.textDim)
        case .blocked, .blocked_by, .unknown:
            EmptyView()
        }
    }

    private func run(_ operation: @escaping () async throws -> Void) {
        guard !isBusy else { return }
        isBusy = true
        Task {
            defer { isBusy = false }
            do { try await operation(); onChanged() }
            catch { }
        }
    }
}
