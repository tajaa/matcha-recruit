import SwiftUI

enum CampaignSheet: Identifiable {
    case create
    case qr(PromoCampaign)
    case design(PromoCampaign)
    case share(PromoCampaign)

    var id: String {
        switch self {
        case .create:
            return "create"
        case .qr(let campaign):
            return "qr-\(campaign.id)"
        case .design(let campaign):
            return "design-\(campaign.id)"
        case .share(let campaign):
            return "share-\(campaign.id)"
        }
    }
}

struct CampaignsView: View {
    @State private var vm = CampaignsViewModel()
    @State private var sheet: CampaignSheet?
    @State private var pendingPush: PromoCampaign?

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
                    CampaignListItem(campaign: campaign, sheet: $sheet, pendingPush: $pendingPush)
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
            case .design(let campaign):
                NavigationStack {
                    CampaignDesignerView(campaignID: campaign.id)
                }
            case .share(let campaign):
                ShareCampaignSheet(campaign: campaign, onPostedToLocals: {})
            }
        }
        .alert(
            "Push this offer?",
            isPresented: $pendingPush.isPresented(),
            presenting: pendingPush,
            actions: pushAlertActions,
            message: pushAlertMessage
        )
    }

    private func pushAlertActions(_ campaign: PromoCampaign) -> some View {
        Group {
            Button("Cancel", role: .cancel) { pendingPush = nil }
            Button("Push") {
                let target = campaign
                pendingPush = nil
                Task { await vm.push(target) }
            }
        }
    }

    private func pushAlertMessage(_ campaign: PromoCampaign) -> some View {
        let miles = campaign.radius_miles.map { String(format: "%.1f", $0) } ?? "a few"
        let store = campaign.store_name ?? "the store"
        return Text("This sends once to followers within \(miles) miles of \(store). It can't be undone.")
    }
}

private extension Binding where Value == PromoCampaign? {
    func isPresented() -> Binding<Bool> {
        Binding<Bool>(get: { wrappedValue != nil }, set: { if !$0 { wrappedValue = nil } })
    }
}

private struct CampaignListItem: View {
    let campaign: PromoCampaign
    @Binding var sheet: CampaignSheet?
    @Binding var pendingPush: PromoCampaign?

    private var isLocation: Bool { campaign.campaign_type == "location" }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Location campaigns are push-only — the claim QR only works for a
            // follower with a fresh in-radius device token, so no QR/scan
            // sheet is offered for them.
            if isLocation {
                CampaignRow(campaign: campaign)
            } else {
                Button { sheet = .qr(campaign) } label: {
                    CampaignRow(campaign: campaign)
                }
                .buttonStyle(.plain)
            }
            Button { sheet = .design(campaign) } label: {
                Label(campaign.has_design ? "Edit flyer" : "Design flyer", systemImage: "paintbrush")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            Button { sheet = .share(campaign) } label: {
                Label("Share campaign", systemImage: "person.3.fill")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            pushStatus
        }
    }

    @ViewBuilder
    private var pushStatus: some View {
        if isLocation, campaign.status == "active", campaign.push_sent_at == nil {
            Button { pendingPush = campaign } label: {
                Label("Push to in-radius followers", systemImage: "location.fill")
            }
            .buttonStyle(.borderedProminent)
            .tint(TU.ember)
        } else if isLocation, campaign.push_sent_at != nil, let sent = campaign.push_sent_count {
            Text("Pushed to \(sent) follower\(sent == 1 ? "" : "s")")
                .font(.interCaption)
                .foregroundStyle(TU.textDim)
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
