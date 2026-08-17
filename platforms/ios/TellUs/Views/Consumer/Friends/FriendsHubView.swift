import SwiftUI

struct FriendsHubView: View {
    @State private var vm: FriendsHubViewModel
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
                    FriendRequestRow(request: request, highlighted: request.id == highlightRequestId)
                }
            }
            Section("Sent") { ForEach(vm.outgoing) { request in FriendRequestRow(request: request, highlighted: false) } }
        }.listStyle(.insetGrouped)
    }

    private var findList: some View {
        List { NavigationLink("Find people") { FriendSearchView() } }
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
    var body: some View {
        HStack { Text(request.person?.display_name ?? "Someone"); Spacer(); Text(request.direction?.rawValue.capitalized ?? "Request").font(.interCaption).foregroundStyle(TU.textDim) }
            .listRowBackground(highlighted ? TU.ember.opacity(0.15) : TU.inkRaised)
    }
}
