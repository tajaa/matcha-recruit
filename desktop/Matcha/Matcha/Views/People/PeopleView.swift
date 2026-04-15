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
            Divider()
            if isLoading {
                Spacer()
                Text("loading…")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else {
                content
            }
        }
        .background(.ultraThinMaterial)
        .task {
            await loadAll()
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 20) {
            ForEach(Tab.allCases) { t in
                Button { tab = t } label: {
                    VStack(spacing: 3) {
                        HStack(spacing: 4) {
                            Text(t.rawValue)
                                .font(.system(size: 11, weight: tab == t ? .medium : .regular, design: .monospaced))
                                .foregroundColor(tab == t ? Color.matcha500 : .white.opacity(0.5))
                            Text("(\(countFor(t)))")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.white.opacity(0.35))
                        }
                        Rectangle()
                            .fill(tab == t ? Color.matcha500 : Color.clear)
                            .frame(height: 1)
                    }
                }
                .buttonStyle(.plain)
            }
            Spacer()
            Button {
                Task { await loadAll() }
            } label: {
                Text("refresh")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
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
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.white.opacity(0.4))
                    Spacer()
                }
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(users) { user in
                            row(user, showActions: showActions)
                            Divider().opacity(0.4)
                        }
                    }
                }
            }
        }
    }

    private func row(_ user: UserConnection, showActions: Bool) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Text(initials(for: user))
                .font(.system(size: 11, weight: .medium, design: .monospaced))
                .foregroundColor(.white.opacity(0.7))
                .frame(width: 32, height: 32)
                .background(Color.white.opacity(0.05))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(user.name.lowercased())
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(1)
                Text(user.email)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
                    .lineLimit(1)
            }

            Spacer()

            if showActions {
                if acting.contains(user.userId) {
                    Text("…")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.white.opacity(0.4))
                } else {
                    Button {
                        Task { await accept(user) }
                    } label: {
                        Text("accept")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(Color.matcha500)
                    }
                    .buttonStyle(.plain)

                    Button {
                        Task { await decline(user) }
                    } label: {
                        Text("decline")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.white.opacity(0.45))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
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
