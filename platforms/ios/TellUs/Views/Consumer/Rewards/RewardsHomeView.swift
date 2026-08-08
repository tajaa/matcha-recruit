import SwiftUI

struct RewardsHomeView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = RewardsHomeViewModel()

    var body: some View {
        ZStack {
            EmberBackground()

            ScrollView {
                VStack(spacing: 20) {
                    ErrorBanner(message: vm.error)

                    if let balance = PointsStore.shared.balance ?? vm.balance {
                        balanceHero(balance)
                            .riseIn(0)
                    }

                    if !vm.badges.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            sectionLabel("Badges")
                            BadgesGrid(badges: vm.badges)
                        }
                        .padding(16)
                        .glassCard()
                        .riseIn(1)
                    }

                    if !vm.recentLedger.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                sectionLabel("Recent activity")
                                Spacer()
                                NavigationLink { LedgerView() } label: {
                                    Text("See all")
                                        .font(TU.eyebrow())
                                        .foregroundStyle(TU.ember)
                                }
                            }
                            VStack(spacing: 0) {
                                ForEach(Array(vm.recentLedger.enumerated()), id: \.element.id) { index, entry in
                                    if index > 0 {
                                        Divider().overlay(.white.opacity(0.06))
                                    }
                                    ledgerRow(entry)
                                }
                            }
                        }
                        .padding(16)
                        .glassCard()
                        .riseIn(2)
                    }
                }
                .padding(.horizontal)
                .padding(.vertical)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("Rewards")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { NotificationsView() } label: {
                    Image(systemName: "bell.fill")
                        .foregroundStyle(.white.opacity(0.85))
                        .overlay(alignment: .topTrailing) {
                            if appState.unreadCount > 0 {
                                Text(appState.unreadCount >= 100 ? "99+" : "\(appState.unreadCount)")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(TU.ember, in: Capsule())
                                    .foregroundStyle(TU.ink)
                                    .offset(x: 10, y: -10)
                            }
                        }
                }
            }
        }
        .refreshable { await vm.load() }
        .task { await vm.load() }
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text.uppercased())
            .font(TU.eyebrow())
            .tracking(1.6)
            .foregroundStyle(TU.textDim)
    }

    private func balanceHero(_ balance: PointsBalance) -> some View {
        VStack(spacing: 16) {
            ZStack {
                EmberRing(progress: balance.levelProgress)
                VStack(spacing: 2) {
                    Text("\(balance.points_balance)")
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                    Text("POINTS")
                        .font(TU.eyebrow(10))
                        .tracking(2)
                        .foregroundStyle(TU.textDim)
                }
            }

            VStack(spacing: 6) {
                Text("LEVEL \(balance.level) · \(balance.points_to_next_level) TO NEXT")
                    .font(TU.eyebrow())
                    .tracking(1.2)
                    .foregroundStyle(TU.textDim)

                if balance.current_streak > 0 {
                    Label("\(balance.current_streak)-day streak", systemImage: "flame.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(TU.emberHot)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
        .glassCard()
    }

    private func ledgerRow(_ entry: LedgerEntry) -> some View {
        HStack {
            Text(entry.description ?? entry.reason.replacingOccurrences(of: "_", with: " ").capitalized)
                .font(.system(size: 14))
                .foregroundStyle(.white.opacity(0.92))
            Spacer()
            Text(entry.delta > 0 ? "+\(entry.delta)" : "\(entry.delta)")
                .font(.system(size: 14, weight: .semibold, design: .monospaced))
                .foregroundStyle(entry.delta >= 0 ? TU.emberHot : .red.opacity(0.85))
        }
        .padding(.vertical, 10)
    }
}
