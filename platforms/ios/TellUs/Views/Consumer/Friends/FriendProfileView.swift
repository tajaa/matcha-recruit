import SwiftUI

struct FriendProfileView: View {
    let accountId: String
    @State private var profile: FriendProfile?
    @State private var error: String?

    var body: some View {
        List {
            if let profile {
                Section {
                    HStack(spacing: 14) {
                        Avatar(profile, size: .header)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(profile.display_name).font(.interTitle3)
                            if let handle = profile.handle { Text("@\(handle)").font(.interCaption).foregroundStyle(TU.textDim) }
                            Text("Level \(profile.level) · \(profile.friend_count) friends").font(.interCaption).foregroundStyle(TU.textDim)
                        }
                    }
                }
                if let reviews = profile.reviews { Section("Reviews") { ForEach(reviews) { review in Text(review.title ?? review.brand_name) } } }
                if let places = profile.followed_places { Section("Places") { ForEach(places) { Text($0.name) } } }
                if let boards = profile.boards { Section("Boards") { ForEach(boards) { Text($0.brand_name) } } }
            } else if error == nil { ProgressView() }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle(profile?.display_name ?? "Profile")
        .task {
            do { profile = try await FriendsService.shared.profile(accountId: accountId) }
            catch { if !error.isCancellation { self.error = error.localizedDescription } }
        }
        .overlay(alignment: .top) { ErrorBanner(message: error).padding(.top, 8) }
    }
}
