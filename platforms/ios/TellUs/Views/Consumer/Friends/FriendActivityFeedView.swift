import SwiftUI

struct FriendActivityFeedView: View {
    @State private var vm = FriendsFeedViewModel()

    var body: some View {
        List {
            ForEach(vm.items) { item in
                if let headline = item.headline {
                    HStack(spacing: 10) {
                        Avatar(item.actor, size: .compact)
                        VStack(alignment: .leading) {
                            Text(headline)
                            if let brand = item.brand_name { Text(brand).font(.interCaption).foregroundStyle(TU.textDim) }
                        }
                    }
                    .task { if item.id == vm.items.last?.id { await vm.loadMore() } }
                    .listRowBackground(TU.inkRaised)
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Friend Activity")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}

private extension FriendActivityItem {
    var headline: String? {
        switch kind {
        case .review_published: return "\(actor.display_name) published a review"
        case .place_followed: return "\(actor.display_name) followed a place"
        case .unknown: return nil
        }
    }
}
