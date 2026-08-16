import SwiftUI

private enum CampaignSheet: Identifiable {
    case create
    case qr(PromoCampaign)

    var id: String {
        switch self {
        case .create:
            return "create"
        case .qr(let campaign):
            return "qr-\(campaign.id)"
        }
    }
}

struct CampaignsView: View {
    @State private var vm = CampaignsViewModel()
    @State private var sheet: CampaignSheet?

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
                    VStack(alignment: .leading, spacing: 8) {
                        Button { sheet = .qr(campaign) } label: {
                            CampaignRow(campaign: campaign)
                        }
                        .buttonStyle(.plain)
                        if campaign.campaign_type == "location", campaign.push_sent_at == nil {
                            Button {
                                Task { await vm.push(campaign) }
                            } label: {
                                Label("Push to in-radius followers", systemImage: "location.fill")
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(TU.ember)
                        } else if campaign.campaign_type == "location", let sent = campaign.push_sent_count {
                            Text("Pushed to \(sent) follower\(sent == 1 ? "" : "s")")
                                .font(.interCaption)
                                .foregroundStyle(TU.textDim)
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Campaigns")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { sheet = .create } label: {
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
        .sheet(item: $sheet) { sheet in
            switch sheet {
            case .create:
                CampaignFormSheet(vm: vm) { created in
                    self.sheet = .qr(created)
                }
            case .qr(let campaign):
                CampaignQRSheet(campaign: campaign)
            }
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
                    .font(.interHeadline)
                    .foregroundStyle(.primary)
                Spacer()
                StatusChip(text: campaign.status, tint: statusColor)
            }

            Text(campaign.reward_text)
                .font(.interSubheadline)
                .foregroundStyle(.secondary)
                .lineLimit(2)

            HStack(spacing: 6) {
                if campaign.campaign_type == "location" {
                    Text("Location · \(campaign.store_name ?? "store") · \(campaign.radius_miles ?? 0, specifier: "%.1f") mi")
                    Text("·")
                }
                Text("\(campaign.claim_count) / \(campaign.max_claims) claimed")
                if let stats = campaign.stats {
                    Text("·")
                    Text("\(stats.redeemed) redeemed")
                    Text("·")
                    Text("\(stats.outstanding) outstanding")
                }
            }
            .font(.interCaption)
            .foregroundStyle(.secondary)

            if let ends = campaign.ends_at {
                Text("Ends \(Formatters.relativeString(from: ends))")
                    .font(.interCaption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 6)
    }
}
