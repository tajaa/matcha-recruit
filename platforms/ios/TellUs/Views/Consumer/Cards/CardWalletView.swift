import SwiftUI

struct CardWalletView: View {
    @State private var vm = PromoCardsViewModel()

    var body: some View {
        Group {
            if vm.isLoading && vm.cards.isEmpty {
                ProgressView().tint(TU.ember)
            } else if vm.cards.isEmpty {
                EmptyState(
                    icon: "ticket",
                    title: "No reward cards yet",
                    hint: "Scan a promo flyer's QR code to claim one."
                )
            } else {
                List {
                    let groups = vm.grouped
                    if !groups.active.isEmpty {
                        Section("Ready to use") {
                            ForEach(groups.active) { CardRow(card: $0) }
                        }
                    }
                    if !groups.past.isEmpty {
                        Section("Past") {
                            ForEach(groups.past) { CardRow(card: $0).opacity(0.55) }
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .background(EmberBackground())
        .navigationTitle("My cards")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) {
            if let error = vm.error { ErrorBanner(message: error) }
        }
    }
}

private struct CardRow: View {
    let card: PromoCard

    var body: some View {
        NavigationLink(value: card) {
            VStack(alignment: .leading, spacing: 4) {
                Text(card.reward_text)
                    .font(.interHeadline)
                    .foregroundStyle(.white)
                Text(card.brand_name)
                    .font(.interSubheadline)
                    .foregroundStyle(TU.textDim)
                HStack(spacing: 6) {
                    StatusChip(text: card.status)
                    if card.status == "issued" {
                        Text("Expires \(Formatters.relativeString(from: card.expires_at))")
                            .font(.interCaption)
                            .foregroundStyle(TU.textDim)
                    } else if let at = card.redeemed_at {
                        Text("Used \(Formatters.relativeString(from: at))")
                            .font(.interCaption)
                            .foregroundStyle(TU.textDim)
                    }
                }
            }
            .padding(.vertical, 4)
        }
        .listRowBackground(TU.inkRaised)
    }
}
