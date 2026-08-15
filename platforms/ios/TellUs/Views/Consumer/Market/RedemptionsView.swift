import SwiftUI

struct RedemptionsView: View {
    @State private var vm = RedemptionsViewModel()

    var body: some View {
        Group {
            if vm.redemptions.isEmpty && !vm.isLoading {
                EmptyState(icon: "ticket", title: "No redemptions yet")
            } else {
                List(vm.redemptions) { redemption in
                    NavigationLink {
                        RedemptionDetailView(redemption: redemption)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(redemption.listing_title ?? "Reward").font(.headline)
                            HStack {
                                if let brand = redemption.brand_name { Text(brand).font(.caption).foregroundStyle(TU.textDim) }
                                Spacer()
                                StatusChip(text: redemption.status.rawValue, tint: color(for: redemption.status))
                            }
                        }
                    }
                    .themedRow()
                }
                .listStyle(.insetGrouped)
                .themedScreen()
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }

    private func color(for status: RedemptionStatus) -> Color {
        switch status {
        case .redeemed: return .green
        case .expired, .cancelled: return .red
        default: return .orange
        }
    }
}
