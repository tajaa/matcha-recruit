import SwiftUI

struct FriendSearchView: View {
    @State private var query = ""
    @State private var results: [FriendSummary] = []
    @State private var error: String?

    var body: some View {
        List {
            Section { TextField("@handle or name", text: $query).textInputAutocapitalization(.never) }
            Section {
                ForEach(results) { person in
                    NavigationLink { FriendProfileView(accountId: person.account_id) } label: { FriendRow(person: person) }
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Find Friends")
        .task(id: query) {
            try? await Task.sleep(for: .milliseconds(450))
            guard query.count >= 2 else { results = []; return }
            do { results = try await FriendsService.shared.search(FriendHandle.normalize(query)) }
            catch { if !error.isCancellation { self.error = error.localizedDescription } }
        }
    }
}
