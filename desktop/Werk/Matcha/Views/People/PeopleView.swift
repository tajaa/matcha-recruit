import SwiftUI

struct PeopleView: View {
    @State private var tab: Tab = .pending
    @State private var connections: [UserConnection] = []
    @State private var pending: [UserConnection] = []
    @State private var sent: [UserConnection] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var acting: Set<String> = []

    enum Tab: String, CaseIterable, Identifiable {
        case pending, friends, sent
        var id: String { rawValue }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            tabBar
            Divider().opacity(0.3)
            if isLoading {
                Spacer()
                Text("Loading…")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            } else {
                content
            }
        }
        .background(Color.appBackground)
        .task {
            await loadAll()
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text("People")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button {
                Task { await loadAll() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .help("Refresh")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private var tabBar: some View {
        HStack(spacing: 4) {
            ForEach(Tab.allCases) { t in
                Button { tab = t } label: {
                    HStack(spacing: 4) {
                        Text(t.rawValue.capitalized)
                            .font(.system(size: 11, weight: .medium))
                        Text("\(countFor(t))")
                            .font(.system(size: 10))
                            .foregroundColor(tab == t ? .white.opacity(0.8) : .secondary)
                    }
                    .foregroundColor(tab == t ? .white : .secondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(tab == t ? Color.matcha500.opacity(0.8) : Color.zinc800)
                    )
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .pending:
            list(pending, emptyMessage: "no pending requests", showActions: true)
        case .friends:
            list(connections, emptyMessage: "no connections yet", showActions: false)
        case .sent:
            list(sent, emptyMessage: "no sent requests", showActions: false)
        }
    }

    private func list(_ users: [UserConnection], emptyMessage: String, showActions: Bool) -> some View {
        Group {
            if users.isEmpty {
                VStack {
                    Spacer()
                    Text(emptyMessage)
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Spacer()
                }
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(users) { user in
                            row(user, showActions: showActions)
                            Divider().opacity(0.25)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private func row(_ user: UserConnection, showActions: Bool) -> some View {
        HStack(alignment: .center, spacing: 10) {
            Text(initials(for: user))
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.secondary)
                .frame(width: 32, height: 32)
                .background(Color.zinc800)
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(user.name)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.primary)
                    .lineLimit(1)
                Text(user.email)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }

            Spacer()

            if showActions {
                if acting.contains(user.userId) {
                    ProgressView().controlSize(.small)
                } else {
                    Button {
                        Task { await accept(user) }
                    } label: {
                        Text("Accept")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.matcha500)
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)

                    Button {
                        Task { await decline(user) }
                    } label: {
                        Text("Decline")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.zinc800)
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Data

    private func countFor(_ t: Tab) -> Int {
        switch t {
        case .pending: return pending.count
        case .friends: return connections.count
        case .sent: return sent.count
        }
    }

    private func initials(for user: UserConnection) -> String {
        let parts = user.name.split(separator: " ")
        if parts.count >= 2 {
            return String((parts[0].first ?? Character(" "))) + String((parts[1].first ?? Character(" ")))
        }
        return String(user.name.prefix(2)).uppercased()
    }

    private func loadAll() async {
        isLoading = true
        errorMessage = nil
        do {
            async let p = ChannelsService.shared.listPendingConnections()
            async let c = ChannelsService.shared.listConnections()
            async let s = ChannelsService.shared.listSentConnections()
            let (pendingRes, connRes, sentRes) = try await (p, c, s)
            pending = pendingRes
            connections = connRes
            sent = sentRes
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func accept(_ user: UserConnection) async {
        acting.insert(user.userId)
        defer { acting.remove(user.userId) }
        do {
            try await ChannelsService.shared.acceptConnection(userId: user.userId)
            await loadAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func decline(_ user: UserConnection) async {
        acting.insert(user.userId)
        defer { acting.remove(user.userId) }
        do {
            try await ChannelsService.shared.declineConnection(userId: user.userId)
            await loadAll()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
