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
        .themedContainer()
        .navigationTitle("Market")
        .navigationDestination(for: PromoCard.self) { CardDetailView(card: $0) }
    }
}
