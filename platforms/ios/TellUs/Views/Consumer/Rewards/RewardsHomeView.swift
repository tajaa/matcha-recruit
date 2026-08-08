import SwiftUI

struct RewardsHomeView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = RewardsHomeViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                ErrorBanner(message: vm.error)

                if let balance = PointsStore.shared.balance ?? vm.balance {
                    VStack(spacing: 12) {
                        Text("\(balance.points_balance)")
                            .font(.system(size: 48, weight: .bold, design: .rounded))
                        Text("points").foregroundStyle(.secondary)
                        LevelProgressBar(progress: balance.levelProgress, level: balance.level)
                            .padding(.horizontal, 32)
                        Text("\(balance.points_to_next_level) to next level")
                            .font(.caption).foregroundStyle(.secondary)
                        if balance.current_streak > 0 {
                            Label("\(balance.current_streak)-day streak", systemImage: "flame.fill")
                                .font(.footnote.bold())
                                .foregroundStyle(.orange)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 24)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal)
                }

                if !vm.badges.isEmpty {
                    BadgesGrid(badges: vm.badges)
                        .padding(.horizontal)
                }

                if !vm.recentLedger.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Recent activity").font(.headline)
                            Spacer()
                            NavigationLink("See all") { LedgerView() }
                                .font(.footnote)
                        }
                        ForEach(vm.recentLedger) { entry in
                            HStack {
                                Text(entry.description ?? entry.reason.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.subheadline)
                                Spacer()
                                Text(entry.delta > 0 ? "+\(entry.delta)" : "\(entry.delta)")
                                    .font(.subheadline.bold())
                                    .foregroundStyle(entry.delta >= 0 ? .green : .red)
                            }
                        }
                    }
                    .padding(.horizontal)
                }
            }
            .padding(.vertical)
        }
        .navigationTitle("Rewards")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { NotificationsView() } label: {
                    Image(systemName: "bell")
                        .overlay(alignment: .topTrailing) {
                            if appState.unreadCount > 0 {
                                Text(appState.unreadCount >= 100 ? "99+" : "\(appState.unreadCount)")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(.red, in: Capsule())
                                    .foregroundStyle(.white)
                                    .offset(x: 10, y: -10)
                            }
                        }
                }
            }
        }
        .refreshable { await vm.load() }
        .task { await vm.load() }
    }
}
