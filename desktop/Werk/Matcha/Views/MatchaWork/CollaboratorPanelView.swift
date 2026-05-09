import SwiftUI

struct CollaboratorPanelView: View {
    let projectId: String

    @State private var collaborators: [MWProjectCollaborator] = []
    @State private var searchText = ""
    @State private var searchResults: [MWAdminSearchUser] = []
    @State private var suggestions: [MWAdminSearchUser] = []
    @State private var friends: [UserConnection] = []
    @State private var isSearching = false
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var searchTimer: Timer?

    /// Friends filtered by the current search text (local filter).
    private var filteredFriends: [UserConnection] {
        let q = searchText.trimmingCharacters(in: .whitespaces).lowercased()
        let list: [UserConnection]
        if q.count >= 2 {
            list = friends.filter { $0.name.lowercased().contains(q) || $0.email.lowercased().contains(q) }
        } else {
            list = friends
        }
        // Exclude anyone already a collaborator.
        return list.filter { friend in
            !collaborators.contains { $0.userId == friend.userId }
        }
    }

    /// Server-side search results or suggestions, excluding friends already
    /// shown in the dedicated section above.
    private var displayedUsers: [MWAdminSearchUser] {
        let base = searchText.count >= 2 ? searchResults : suggestions
        let friendIds = Set(friends.map(\.userId))
        return base.filter { !friendIds.contains($0.id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Collaborators")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.top, 14)
                .padding(.bottom, 10)

            Divider().opacity(0.3)

            // Search
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass").font(.system(size: 11)).foregroundColor(.secondary)
                TextField("Search users to add...", text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .onChange(of: searchText) { scheduleSearch() }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.zinc800.opacity(0.5))

            ScrollView {
                VStack(spacing: 0) {
                    // ── Friends section ──────────────────────────────
                    if !filteredFriends.isEmpty {
                        sectionHeader("Friends")
                        ForEach(filteredFriends) { friend in
                            let alreadyAdded = collaborators.contains { $0.userId == friend.userId }
                            Button {
                                guard !alreadyAdded else { return }
                                Task { await addUser(userId: friend.userId) }
                            } label: {
                                userRow(
                                    name: friend.name,
                                    email: friend.email,
                                    badgeColor: .matcha500,
                                    alreadyAdded: alreadyAdded
                                )
                            }
                            .buttonStyle(.plain)
                            .disabled(alreadyAdded)
                        }
                        Divider().opacity(0.3)
                    }

                    // ── Search results / Suggestions section ─────────
                    if !displayedUsers.isEmpty {
                        sectionHeader(searchText.count >= 2 ? "Results" : "Suggestions")
                        ForEach(displayedUsers) { user in
                            let alreadyAdded = collaborators.contains { $0.userId == user.id }
                            Button {
                                guard !alreadyAdded else { return }
                                Task { await addUser(userId: user.id) }
                            } label: {
                                userRow(
                                    name: user.name,
                                    email: user.email,
                                    badgeColor: .matcha500,
                                    alreadyAdded: alreadyAdded
                                )
                            }
                            .buttonStyle(.plain)
                            .disabled(alreadyAdded)
                        }
                    }

                    // ── Empty state ──────────────────────────────────
                    if filteredFriends.isEmpty && displayedUsers.isEmpty && searchText.count >= 2 && !isSearching {
                        Text("No users found.")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                    }
                }
                .background(Color.zinc800.opacity(0.3))
            }
            .frame(maxHeight: 160)

            Divider().opacity(0.3)

            // Current collaborators
            if isLoading {
                Spacer()
                HStack { Spacer(); ProgressView().tint(.secondary); Spacer() }
                Spacer()
            } else {
                ScrollView {
                    VStack(spacing: 1) {
                        ForEach(collaborators) { collab in
                            HStack(spacing: 8) {
                                Circle().fill(Color.matcha600).frame(width: 28, height: 28)
                                    .overlay(Text(String(collab.name.prefix(1)).uppercased()).font(.system(size: 11, weight: .bold)).foregroundColor(.white))
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(collab.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                                    Text(collab.email).font(.system(size: 10)).foregroundColor(.secondary)
                                }
                                Spacer()
                                if let role = collab.role {
                                    Text(role)
                                        .font(.system(size: 9, weight: .medium))
                                        .foregroundColor(role == "owner" ? .matcha500 : .secondary)
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background((role == "owner" ? Color.matcha500 : Color.secondary).opacity(0.12))
                                        .cornerRadius(4)
                                }
                                if collab.role != "owner" {
                                    Button {
                                        Task { await removeUser(userId: collab.userId) }
                                    } label: {
                                        Image(systemName: "xmark").font(.system(size: 10)).foregroundColor(.secondary)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 6)
                        }
                    }
                    .padding(.vertical, 8)
                }
            }

            if let err = errorMessage {
                Text(err).font(.system(size: 10)).foregroundColor(.red)
                    .padding(.horizontal, 16).padding(.bottom, 8)
            }
        }
        .background(Color.appBackground)
        .task {
            await load()
            await loadFriends()
            await loadSuggestions()
        }
    }

    // MARK: - Reusable row components

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 9, weight: .semibold))
            .foregroundColor(.secondary)
            .tracking(0.5)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.top, 6)
            .padding(.bottom, 2)
    }

    private func userRow(name: String, email: String, badgeColor: Color, alreadyAdded: Bool) -> some View {
        HStack(spacing: 8) {
            Circle().fill(badgeColor).frame(width: 24, height: 24)
                .overlay(Text(String(name.prefix(1)).uppercased()).font(.system(size: 10, weight: .bold)).foregroundColor(.white))
            VStack(alignment: .leading, spacing: 1) {
                Text(name).font(.system(size: 12)).foregroundColor(.white)
                Text(email).font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer()
            if alreadyAdded {
                Text("Added").font(.system(size: 10)).foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }

    // MARK: - Data loading

    private func loadFriends() async {
        do {
            let f = try await ChannelsService.shared.listConnections()
            await MainActor.run { friends = f }
        } catch {
            // Silent — friends are supplemental. Suggestions still work.
        }
    }

    private func loadSuggestions() async {
        do {
            // Empty query returns invitable users (friends, inbox contacts,
            // company peers, prior collaborators, admins) sorted by name.
            let s = try await MatchaWorkService.shared.searchInvitableUsers(query: "")
            await MainActor.run { suggestions = s }
        } catch {
            // Silent — suggestions are optional. Search still works.
        }
    }

    private func load() async {
        do {
            let c = try await MatchaWorkService.shared.listCollaborators(projectId: projectId)
            await MainActor.run { collaborators = c; isLoading = false }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription; isLoading = false }
        }
    }

    private func addUser(userId: String) async {
        do {
            try await MatchaWorkService.shared.addCollaborator(projectId: projectId, userId: userId)
            await load()
            await MainActor.run { searchText = ""; searchResults = [] }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    private func removeUser(userId: String) async {
        do {
            try await MatchaWorkService.shared.removeCollaborator(projectId: projectId, userId: userId)
            await MainActor.run { collaborators.removeAll { $0.userId == userId } }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    private func scheduleSearch() {
        searchTimer?.invalidate()
        guard searchText.count >= 2 else { searchResults = []; return }
        searchTimer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: false) { _ in
            Task {
                let q = searchText
                do {
                    let results = try await MatchaWorkService.shared.searchInvitableUsers(query: q)
                    await MainActor.run { searchResults = results }
                } catch {
                    await MainActor.run { searchResults = [] }
                }
            }
        }
    }
}
