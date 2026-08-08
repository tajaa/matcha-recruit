import SwiftUI

struct MarketplaceHomeView: View {
    @State private var tab = 0

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $tab) {
                Text("Marketplace").tag(0)
                Text("My Redemptions").tag(1)
            }
            .pickerStyle(.segmented)
            .padding()

            if tab == 0 { MarketplaceView() } else { RedemptionsView() }
        }
        .navigationTitle("Market")
    }
}
