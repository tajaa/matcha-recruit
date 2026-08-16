import SwiftUI

enum CampaignSheet: Identifiable {
    case create
    case qr(PromoCampaign)
    case design(PromoCampaign)
    case share(PromoCampaign)
    case guide

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
        case .guide:
            return "guide"
        }
    }
}

struct CampaignsView: View {
    @Environment(AppState.self) private var appState
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
            ToolbarItem(placement: .topBarTrailing) {
                Button { sheet = .guide } label: {
                    Image(systemName: "info.circle")
                }
                .accessibilityLabel("How campaigns work")
            }
        }
        .task {
            await vm.load()
            showGuideIfNeeded()
        }
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
            case .guide:
                BrandCampaignGuide(
                    onCreateCampaign: {
                        completeGuide()
                        self.sheet = .create
                    },
                    onDone: { completeGuide() }
                )
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

    private var guideKey: String? {
        guard let accountID = appState.account?.id else { return nil }
        return "tellus.brand-campaign-guide.v1:\(accountID)"
    }

    private func showGuideIfNeeded() {
        guard sheet == nil, let guideKey, !UserDefaults.standard.bool(forKey: guideKey) else { return }
        sheet = .guide
    }

    private func completeGuide() {
        if let guideKey { UserDefaults.standard.set(true, forKey: guideKey) }
        sheet = nil
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

private struct BrandCampaignGuide: View {
    let onCreateCampaign: () -> Void
    let onDone: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var stepIndex = 0
    @State private var didExit = false

    private let steps = [
        (icon: "ticket.fill", eyebrow: "1 · Build the offer", title: "Start with a campaign", body: "Create a QR campaign for flyers and Locals, or choose a location campaign to reach nearby followers with a one-time push."),
        (icon: "sparkles", eyebrow: "2 · Make it yours", title: "Design the flyer", body: "Choose a template, palette, stickers, or your logo. Drag, resize, and rotate layers, then export the finished flyer or use it on the campaign."),
        (icon: "person.3.fill", eyebrow: "3 · Share with regulars", title: "Post QR offers to Locals", body: "Use Share campaign, then Post to Locals. Members see the flyer and can open the claim link from the board."),
        (icon: "location.fill", eyebrow: "4 · Reach nearby", title: "Push location offers", body: "Location campaigns stay push-only. Send them to followers with a fresh device location inside your configured radius."),
    ]

    private var current: (icon: String, eyebrow: String, title: String, body: String) { steps[stepIndex] }
    private var isLast: Bool { stepIndex == steps.count - 1 }

    private func finish() {
        didExit = true
        onDone()
    }

    private func createCampaign() {
        didExit = true
        onCreateCampaign()
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                ProgressView(value: Double(stepIndex + 1), total: Double(steps.count))
                    .tint(TU.ember)

                Image(systemName: current.icon)
                    .font(.system(size: 42, weight: .semibold))
                    .foregroundStyle(TU.ember)
                    .frame(width: 84, height: 84)
                    .background(TU.ember.opacity(0.14), in: RoundedRectangle(cornerRadius: 22))

                VStack(spacing: 8) {
                    Text(current.eyebrow)
                        .font(TU.eyebrow())
                        .foregroundStyle(TU.emberHot)
                    Text(current.title)
                        .font(.interTitle3.bold())
                        .multilineTextAlignment(.center)
                    Text(current.body)
                        .font(.interBody)
                        .foregroundStyle(TU.textDim)
                        .multilineTextAlignment(.center)
                }

                Spacer()

                HStack(spacing: 10) {
                    if stepIndex > 0 {
                        Button("Back") { stepIndex -= 1 }
                            .buttonStyle(.bordered)
                    }
                    Spacer()
                    if stepIndex == 0 {
                        Button("Create campaign") { createCampaign() }
                            .buttonStyle(EmberButtonStyle())
                    }
                    Button(isLast ? "Finish" : "Next") {
                        if isLast {
                            finish()
                        } else {
                            stepIndex += 1
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(TU.ember)
                }
            }
            .padding()
            .navigationTitle("Campaigns, in four moves")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Skip") { finish(); dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .onDisappear {
            if !didExit { finish() }
        }
    }
}
