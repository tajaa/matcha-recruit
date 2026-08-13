import SwiftUI

struct CampaignsView: View {
    @State private var vm = CampaignsViewModel()
    @State private var showNew = false
    @State private var selectedCampaign: PromoCampaign?
    @State private var campaignAwaitingQR: PromoCampaign?

    var body: some View {
        Group {
            if vm.isLoading && vm.campaigns.isEmpty {
                ProgressView()
            } else if vm.campaigns.isEmpty {
                EmptyState(
                    icon: "megaphone",
                    title: "No campaigns yet",
                    hint: "Create one to generate a claimable QR code."
                )
            } else {
                List(vm.campaigns) { campaign in
                    Button { selectedCampaign = campaign } label: {
                        CampaignRow(campaign: campaign)
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Campaigns")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showNew = true } label: {
                    Image(systemName: "plus")
                }
                .accessibilityLabel("New campaign")
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) {
            ErrorBanner(message: vm.error).padding(.top, 8)
        }
        .sheet(isPresented: $showNew, onDismiss: {
            selectedCampaign = campaignAwaitingQR
            campaignAwaitingQR = nil
        }) {
            CampaignFormSheet(vm: vm) { created in
                campaignAwaitingQR = created
            }
        }
        .sheet(item: $selectedCampaign) { campaign in
            CampaignQRSheet(campaign: campaign)
        }
    }
}

private struct CampaignRow: View {
    let campaign: PromoCampaign

    private var statusColor: Color {
        switch campaign.status {
        case "active": return .green
        case "cancelled": return .red
        default: return .secondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(campaign.title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                Spacer()
                StatusChip(text: campaign.status, tint: statusColor)
            }

            Text(campaign.reward_text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2)

            HStack(spacing: 6) {
                Text("\(campaign.claim_count) / \(campaign.max_claims) claimed")
                if let stats = campaign.stats {
                    Text("·")
                    Text("\(stats.redeemed) redeemed")
                    Text("·")
                    Text("\(stats.outstanding) outstanding")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            if let ends = campaign.ends_at {
                Text("Ends \(Formatters.relativeString(from: ends))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
    }
}
