import SwiftUI

struct LeaderboardView: View {
    @State private var vm = LeaderboardViewModel()

    var body: some View {
        Group {
            if vm.entries.isEmpty && !vm.isLoading {
                EmptyState(icon: "trophy", title: "No leaderboard data yet")
            } else {
                List(vm.entries) { entry in
                    HStack {
                        Text("#\(entry.rank)")
                            .font(.headline)
                            .frame(width: 36, alignment: .leading)
                        VStack(alignment: .leading) {
                            Text(entry.display_name).font(.subheadline.bold())
                            Text("Level \(entry.level)").font(.caption).foregroundStyle(TU.textDim)
                        }
                        Spacer()
                        Text("\(entry.lifetime_points) pts").font(.subheadline.bold())
                    }
                    .listRowBackground(entry.is_you ? TU.ember.opacity(0.15) : TU.inkRaised)
                }
                .listStyle(.insetGrouped)
                .themedScreen()
            }
        }
        .navigationTitle("Leaderboard")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
