import Foundation
import Observation

@MainActor
@Observable
final class FriendsHubViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var tab: FriendsTab = .friends
    var friends: [FriendSummary] = []
    var incoming: [FriendRequest] = []
    var outgoing: [FriendRequest] = []

    func load() async {
        await withLoad {
            async let friendPage = FriendsService.shared.friends()
            async let incoming = FriendsService.shared.requests(direction: .incoming)
            async let outgoing = FriendsService.shared.requests(direction: .outgoing)
            self.friends = try await friendPage.entries
            self.incoming = try await incoming
            self.outgoing = try await outgoing
        }
    }
}
