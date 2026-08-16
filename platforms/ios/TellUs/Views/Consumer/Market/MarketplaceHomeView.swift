import SwiftUI

struct MarketplaceHomeView: View {
    var body: some View {
        List {
            Section {
                ForEach(RewardsSection.allCases) { section in
                    NavigationLink {
                        RewardsSectionScreen(section: section)
                    } label: {
                        RewardsSectionRow(section: section)
                    }
                    .themedRow()
                }
            } footer: {
                Text("Choose a section to browse local offers, cards, and your redemption history.")
                    .font(.interCaption)
                    .foregroundStyle(TU.textDim)
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Rewards")
    }
}

private enum RewardsSection: String, CaseIterable, Identifiable {
    case overview, marketplace, cards, redemptions

    var id: String { rawValue }

    var title: String {
        switch self {
        case .overview: return "Overview"
        case .marketplace: return "Marketplace"
        case .cards: return "Reward cards"
        case .redemptions: return "Redemptions"
        }
    }

    var subtitle: String {
        switch self {
        case .overview: return "Points, badges, and recent activity"
        case .marketplace: return "Find local offers to redeem"
        case .cards: return "Open your active promo cards"
        case .redemptions: return "See your redeemed offers"
        }
    }

    var icon: String {
        switch self {
        case .overview: return "chart.bar.xaxis"
        case .marketplace: return "gift"
        case .cards: return "ticket"
        case .redemptions: return "clock.arrow.circlepath"
        }
    }
}

private struct RewardsSectionRow: View {
    let section: RewardsSection

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: section.icon)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(TU.ember)
                .frame(width: 30, height: 30)
                .background(TU.ember.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(section.title).font(.interBody)
                Text(section.subtitle).font(.interCaption).foregroundStyle(TU.textDim)
            }
        }
        .padding(.vertical, 6)
    }
}

private struct RewardsSectionScreen: View {
    let section: RewardsSection

    var body: some View {
        Group {
            switch section {
            case .overview: RewardsHomeView()
            case .marketplace: MarketplaceView()
            case .cards: CardWalletView()
            case .redemptions: RedemptionsView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .themedContainer()
        .navigationTitle(section.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
