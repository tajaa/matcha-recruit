import SwiftUI

struct InviteToChannelSheet: View {
    let channelId: String
    let channelName: String
    let onInvited: (Int) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var users: [ChannelsService.InvitableUser] = []
    @State private var selectedIds: Set<String> = []
    @State private var loading = false
    @State private var inviting = false
    @State private var error: String?
    @State private var searchTask: Task<Void, Never>?
    @State private var emailInviting = false
    @State private var emailInviteSent: String?

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Loose email check — good enough to decide whether to offer an email
    /// invite; the server validates for real.
    private var queryIsEmail: Bool {
        let q = trimmedQuery
        guard let at = q.firstIndex(of: "@"), at != q.startIndex else { return false }
        let domain = q[q.index(after: at)...]
        return domain.contains(".") && !domain.hasSuffix(".") && !q.contains(" ")
    }

    /// Offer "invite by email" when the query is an email that doesn't already
    /// match an existing user (those go through the normal add-member path).
    private var showEmailInvite: Bool {
        queryIsEmail && !users.contains { $0.email.lowercased() == trimmedQuery.lowercased() }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Invite to #\(channelName)")
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

            Divider().opacity(0.3)

            if showEmailInvite || !users.isEmpty {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        // When the query is an email with no existing user, offer
                        // to send a free-signup link — the invitee joins on signup.
                        if showEmailInvite {
                            emailInviteRow
                            Divider().opacity(0.15)
                        }
                        ForEach(users) { user in
                            UserRow(
                                user: user,
                                selected: selectedIds.contains(user.id)
                            ) {
                                toggle(user.id)
                            }
                            Divider().opacity(0.15)
                        }
                    }
                }
            } else if !loading {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.questionmark")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary)
                    Text(query.isEmpty ? "Type to search by name or email" : "No matching users")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(24)
            }

            Divider().opacity(0.3)

            HStack {
                if let err = error {
                    Text(err)
                        .font(.system(size: 11))
                        .foregroundColor(.red)
                } else if let sent = emailInviteSent {
                    Label("Invite sent to \(sent)", systemImage: "checkmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundColor(Color.matcha500)
                        .lineLimit(1)
                }
                Spacer()
                Text("\(selectedIds.count) selected")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Button {
                    Task { await invite() }
                } label: {
                    if inviting {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Invite")
                            .font(.system(size: 12, weight: .medium))
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .disabled(selectedIds.isEmpty || inviting)
            }
            .padding(14)
        }
        .frame(width: 420, height: 500)
        .background(Color.appBackground)
        .task {
            await search("")
        }
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
        // Clear any stale error from a previous keystroke whose request was
        // cancelled by the debounce. Without this, "cancelled" stays visible
        // even when the final search returns 0 legitimate results, making it
        // look like the search is broken when it isn't.
        error = nil
        defer { loading = false }
        do {
            users = try await ChannelsService.shared.searchInvitableUsers(query: q, channelId: channelId)
        } catch is CancellationError {
            // Debounced cancellation is expected; don't surface as an error.
            return
        } catch {
            let nsErr = error as NSError
            // URLSession cancellation surfaces as NSURLErrorCancelled (-999).
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                return
            }
            // keep prior list; surface via inline error
            self.error = error.localizedDescription
        }
    }

    private func toggle(_ id: String) {
        if selectedIds.contains(id) {
            selectedIds.remove(id)
        } else {
            selectedIds.insert(id)
        }
    }

    private func invite() async {
        inviting = true
        error = nil
        defer { inviting = false }
        do {
            let res = try await ChannelsService.shared.addMembers(
                channelId: channelId,
                userIds: Array(selectedIds)
            )
            let addedCount = res.added?.count ?? selectedIds.count
            onInvited(addedCount)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private var emailInviteRow: some View {
        Button {
            Task { await inviteByEmail() }
        } label: {
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Color.matcha500.opacity(0.18))
                        .frame(width: 28, height: 28)
                    Image(systemName: "envelope.fill")
                        .font(.system(size: 11))
                        .foregroundColor(Color.matcha500)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Invite \(trimmedQuery)")
                        .font(.system(size: 12))
                        .foregroundColor(.white)
                    Text("Send a free signup link — they join on sign up")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                Spacer()
                if emailInviting {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Send")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Color.matcha500)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(emailInviting)
    }

    private func inviteByEmail() async {
        let target = trimmedQuery
        guard queryIsEmail else { return }
        emailInviting = true
        error = nil
        emailInviteSent = nil
        defer { emailInviting = false }
        do {
            let res = try await ChannelsService.shared.sendEmailInvites(channelId: channelId, emails: [target])
            if res.invited.contains(where: { $0.lowercased() == target.lowercased() }) {
                emailInviteSent = target
                query = ""
                users = []
            } else if res.alreadyMembers.contains(where: { $0.lowercased() == target.lowercased() }) {
                error = "\(target) is already a member"
            } else {
                error = "Couldn't send invite to \(target)"
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct UserRow: View {
    let user: ChannelsService.InvitableUser
    let selected: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(Color.matcha500.opacity(0.4))
                        .frame(width: 28, height: 28)
                    Text(String(user.name.prefix(1)).uppercased())
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(user.name).font(.system(size: 12)).foregroundColor(.white)
                    Text(user.email).font(.system(size: 10)).foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16))
                    .foregroundColor(selected ? Color.matcha500 : .secondary.opacity(0.5))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? Color.matcha600.opacity(0.06) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
