import Foundation

enum FriendsTab: String, CaseIterable, Identifiable {
    case friends, requests, find
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
}
