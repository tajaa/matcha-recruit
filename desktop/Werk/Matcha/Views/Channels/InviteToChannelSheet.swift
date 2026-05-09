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

            if users.isEmpty && !loading {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.questionmark")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary)
                    Text(query.isEmpty ? "Type to search" : "No matching users")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(24)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
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
            }

            Divider().opacity(0.3)

            HStack {
                if let err = error {
                    Text(err)
                        .font(.system(size: 11))
                        .foregroundColor(.red)
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
