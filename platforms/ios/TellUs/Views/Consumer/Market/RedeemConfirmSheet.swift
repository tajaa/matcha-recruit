import SwiftUI

struct RedeemConfirmSheet: View {
    let listing: Listing
    @Bindable var flow: RedeemFlowModel
    @Environment(\.dismiss) private var dismiss

    private var balance: Int? { PointsStore.shared.balance?.points_balance }
    private var insufficientBalance: Bool {
        guard let balance else { return false }
        return balance < listing.points_cost
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text(listing.title).font(.title2.bold())
                if let description = listing.description {
                    Text(description).foregroundStyle(TU.textDim)
                }
                PointsPill(points: listing.points_cost)
                if let balance {
                    Text("Your balance: \(balance) pts")
                        .font(.footnote)
                        .foregroundStyle(insufficientBalance ? .red : TU.textDim)
                }
                if let terms = listing.terms {
                    Text(terms).font(.caption).foregroundStyle(TU.textDim)
                }

                ErrorBanner(message: flow.error)

                if let redemption = flow.lastRedemption {
                    VStack(spacing: 8) {
                        Text("Redeemed!").font(.headline).foregroundStyle(.green)
                        if let code = redemption.code {
                            Text(code).font(.system(.title3, design: .monospaced))
                        }
                        if let expires = redemption.expires_at {
                            Text("Expires \(Formatters.relativeString(from: expires))")
                                .font(.caption).foregroundStyle(TU.textDim)
                        }
                    }
                    Button("Done") { dismiss() }.buttonStyle(EmberButtonStyle())
                } else {
                    Button {
                        Task { await flow.redeem(listing) }
                    } label: {
                        if flow.isRedeeming { ProgressView().tint(TU.ink) }
                        else { Text("Redeem for \(listing.points_cost) points").bold() }
                    }
                    .buttonStyle(EmberButtonStyle(enabled: !insufficientBalance))
                    .disabled(insufficientBalance || flow.isRedeeming)
                }
            }
            .padding()
            .navigationTitle("Confirm redemption")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
            .themedContainer()
        }
        .presentationDetents([.medium])
    }
}
