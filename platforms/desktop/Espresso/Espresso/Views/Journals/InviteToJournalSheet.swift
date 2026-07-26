import SwiftUI

/// Invite collaborators to a journal. Mirrors `InviteToChannelSheet`'s
/// shape — debounced search, multi-select, batch-invite — but calls the
/// journal collaborator endpoints. Search reuses the same invitable-user
/// pool as channels via `searchInvitableUsers`.
struct InviteToJournalSheet: View {
    let journalId: String
    let journalTitle: String
    let onInvited: (Int) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var query = ""
    @State private var users: [MWAdminSearchUser] = []
    @State private var selectedIds: Set<String> = []
    @State private var loading = false
    @State private var inviting = false
    @State private var error: String?
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            searchBar
            Divider().opacity(0.3)
            list
            Divider().opacity(0.3)
            footer
        }
        .frame(width: 420, height: 480)
        .background(Color.appBackground)
        .task { await search("") }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("Invite to journal")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text(journalTitle)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Button("Close") { dismiss() }
                .buttonStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
        }
        .padding(14)
    }

    private var searchBar: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
            TextField("Search by name or email", text: $query)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white)
                .onChange(of: query) { _, newValue in scheduleSearch(newValue) }
            if loading {
                ProgressView().controlSize(.small)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color.zinc800.opacity(0.5))
    }

    @ViewBuilder
    private var list: some View {
        if users.isEmpty && !loading {
            VStack(spacing: 8) {
                Spacer()
                Image(systemName: "person.crop.circle.badge.questionmark")
                    .font(.system(size: 22))
                    .foregroundColor(.secondary)
                Text(query.isEmpty ? "Type to search" : "No matching users")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            }
        } else {
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(users) { user in
                        row(user: user)
                        Divider().opacity(0.1)
                    }
                }
            }
        }
    }

    private func row(user: MWAdminSearchUser) -> some View {
        let selected = selectedIds.contains(user.id)
        return Button {
            if selected { selectedIds.remove(user.id) } else { selectedIds.insert(user.id) }
        } label: {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.matcha500.opacity(0.4)).frame(width: 26, height: 26)
                    Text(String(user.name.prefix(1)).uppercased())
                        .font(.system(size: 11, weight: .bold)).foregroundColor(.white)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(user.name).font(.system(size: 12)).foregroundColor(.white)
                    Text(user.email).font(.system(size: 10)).foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(selected ? Color.matcha500 : .secondary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
        }
        .buttonStyle(.plain)
    }

    private var footer: some View {
        HStack {
            if let error {
                Text(error).font(.system(size: 10)).foregroundColor(.red.opacity(0.85))
            }
            Spacer()
            Text("\(selectedIds.count) selected").font(.system(size: 10)).foregroundColor(.secondary)
            Button {
                Task { await invite() }
            } label: {
                if inviting {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Invite").font(.system(size: 12, weight: .semibold))
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(Color.matcha600)
            .controlSize(.small)
            .disabled(inviting || selectedIds.isEmpty)
        }
        .padding(12)
    }

    private func scheduleSearch(_ q: String) {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(220))
            if Task.isCancelled { return }
            await search(q)
        }
    }

    private func search(_ q: String) async {
        loading = true
        defer { loading = false }
        do {
            users = try await MatchaWorkService.shared.searchInvitableUsers(query: q)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func invite() async {
        inviting = true
        error = nil
        defer { inviting = false }
        do {
            try await MatchaWorkService.shared.addJournalCollaborators(
                journalId: journalId, userIds: Array(selectedIds),
            )
            onInvited(selectedIds.count)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
