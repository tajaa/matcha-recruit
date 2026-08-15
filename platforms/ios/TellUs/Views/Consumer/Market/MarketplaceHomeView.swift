import SwiftUI

struct MarketplaceHomeView: View {
    @State private var tab = 0

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text("Marketplace").tag(0)
                Text("Redemptions").tag(1)
                Text("Cards").tag(2)
            }
            .pickerStyle(.segmented)
            .tint(TU.ember)
            .padding()

            switch tab {
            case 0: MarketplaceView()
            case 1: RedemptionsView()
            default: CardWalletView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .themedContainer()
        .navigationTitle("Rewards")
        .navigationDestination(for: PromoCard.self) { CardDetailView(card: $0) }
    }
}
