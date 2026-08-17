import SwiftUI

struct FriendsHubView: View {
    @State private var vm: FriendsHubViewModel
    @State private var showInvite = false
    private let highlightRequestId: String?

    init(initialTab: FriendsTab = .friends, highlightRequestId: String? = nil) {
        _vm = State(initialValue: FriendsHubViewModel())
        self.highlightRequestId = highlightRequestId
        _vm.wrappedValue.tab = initialTab
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("Friends", selection: $vm.tab) {
                ForEach(FriendsTab.allCases) { tab in Text(tab.title).tag(tab) }
            }
            .pickerStyle(.segmented)
            .padding()
            .background(TU.ink)
            switch vm.tab {
            case .friends: friendsList
            case .requests: requestsList
            case .find: findList
            }
        }
        .themedScreen()
        .navigationTitle("Friends")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showInvite = true } label: { Image(systemName: "qrcode") }
            }
        }
        .sheet(isPresented: $showInvite) { FriendInviteSheet() }
        .overlay(alignment: .top) {
            if let error = vm.error { ErrorBanner(message: error).padding(.top, 8) }
        }
    }

    private var friendsList: some View {
        List {
            NavigationLink("Friend activity") { FriendActivityFeedView() }.listRowBackground(TU.inkRaised)
            if vm.friends.isEmpty { Text("No friends yet.").foregroundStyle(TU.textDim) }
            ForEach(vm.friends) { person in
                NavigationLink { FriendProfileView(accountId: person.account_id) } label: {
                    FriendRow(person: person)
                }
                .listRowBackground(TU.inkRaised)
            }
        }.listStyle(.insetGrouped)
    }

    private var requestsList: some View {
        List {
            Section("Incoming") {
                ForEach(vm.incoming) { request in
                    FriendRequestRow(request: request, highlighted: request.id == highlightRequestId) {
                        Task { await vm.load() }
                    }
                }
            }
            Section("Sent") {
                ForEach(vm.outgoing) { request in
                    FriendRequestRow(request: request, highlighted: false) {
                        Task { await vm.load() }
                    }
                }
            }
        }.listStyle(.insetGrouped)
    }

    private var findList: some View {
        List {
            NavigationLink("Find people") { FriendSearchView() }
            NavigationLink("Redeem invite") { FriendInviteRedeemView(token: "") }
        }
            .listStyle(.insetGrouped)
    }
}

struct FriendRow: View {
    let person: FriendSummary
    var body: some View {
        HStack(spacing: 12) { Avatar(person, size: .row); VStack(alignment: .leading) { Text(person.display_name); if let handle = person.handle { Text("@\(handle)").font(.interCaption).foregroundStyle(TU.textDim) } } }
    }
}

struct FriendRequestRow: View {
    let request: FriendRequest
    let highlighted: Bool
    let onChanged: () -> Void
    @State private var isBusy = false

    var body: some View {
        HStack {
            Avatar(request.person ?? FriendSummary(account_id: request.direction == .incoming ? request.requester_account_id : request.addressee_account_id), size: .row)
            VStack(alignment: .leading) {
                Text(request.person?.display_name ?? "Someone")
                Text(request.direction?.rawValue.capitalized ?? "Request").font(.interCaption).foregroundStyle(TU.textDim)
            }
            Spacer()
            if request.direction == .incoming {
                Button("Accept") { run { _ = try await FriendsService.shared.accept(requestId: request.id) } }
                Button("Decline", role: .destructive) { run { try await FriendsService.shared.decline(requestId: request.id) } }
            } else {
                Button("Cancel", role: .destructive) { run { try await FriendsService.shared.cancel(requestId: request.id) } }
            }
        }
        .disabled(isBusy)
        .listRowBackground(highlighted ? TU.ember.opacity(0.15) : TU.inkRaised)
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
