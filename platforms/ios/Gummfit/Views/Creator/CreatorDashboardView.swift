import SwiftUI
import Observation

@MainActor
@Observable
final class CreatorDashboardViewModel {
    var profile: CreatorProfileMe?
    var offers: [OfferListItem] = []
    var earnings: [EarningsRow] = []
    var isLoading = false

    var offersNeedingResponse: [OfferListItem] {
        offers.filter { ["sent", "negotiating"].contains($0.status) }
    }

    var activeDeals: [OfferListItem] {
        offers.filter { ["accepted", "active"].contains($0.status) }
    }

    var pendingEarnings: Int {
        earnings
            .filter { $0.status != "paid" }
            .reduce(0) { $0 + $1.amount_cents - ($1.fee_cents ?? 0) }
    }

    var profileIsReady: Bool {
        guard let profile else { return false }
        return profile.bio?.isEmpty == false
            && !profile.socials.isEmpty
            && !profile.portfolio.isEmpty
            && !profile.rates.isEmpty
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }

        async let loadedProfile = try? CreatorService.shared.me()
        async let loadedOffers = try? CollabService.shared.offers().offers
        async let loadedEarnings = try? CreatorService.shared.earnings()

        profile = await loadedProfile
        offers = await loadedOffers ?? []
        earnings = await loadedEarnings ?? []
    }
}

struct CreatorDashboardView: View {
    let onSelect: (CreatorTab) -> Void

    @State private var vm = CreatorDashboardViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    creatorHeader
                    if vm.isLoading && vm.profile == nil {
                        ProgressView()
                            .tint(GummfitTheme.accent)
                            .frame(maxWidth: .infinity, minHeight: 120)
                    } else {
                        attentionSection
                        overviewSection
                        profileSection
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }
            .navigationTitle("Home")
            .navigationBarTitleDisplayMode(.inline)
            .gummfitScreenChrome()
            .refreshable { await vm.load() }
            .task { await vm.load() }
        }
    }

    private var creatorHeader: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(vm.profile?.display_name ?? "Creator workspace")
                .font(.title2.bold())
                .foregroundStyle(GummfitTheme.textPrimary)
            Text(vm.profile?.open_to_offers == true ? "Open to new partnerships" : "Manage your collaborations and earnings")
                .font(.subheadline)
                .foregroundStyle(GummfitTheme.textDim)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gummfitCard(padding: 20)
    }

    @ViewBuilder
    private var attentionSection: some View {
        if !vm.offersNeedingResponse.isEmpty || !vm.profileIsReady {
            VStack(alignment: .leading, spacing: 12) {
                Label("Needs your attention", systemImage: "exclamationmark.circle.fill")
                    .font(.headline)
                    .foregroundStyle(GummfitTheme.warning)

                if !vm.offersNeedingResponse.isEmpty {
                    dashboardAction(
                        "Respond to \(vm.offersNeedingResponse.count) offer\(vm.offersNeedingResponse.count == 1 ? "" : "s")",
                        detail: vm.offersNeedingResponse.first?.title ?? "Review partnership terms",
                        icon: "star.bubble.fill",
                        destination: .deals
                    )
                }

                if !vm.profileIsReady {
                    dashboardAction(
                        "Complete your creator profile",
                        detail: "Add your bio, portfolio, socials, and rates to be discoverable.",
                        icon: "person.crop.circle.badge.exclamationmark",
                        destination: .profile
                    )
                }
            }
            .gummfitCard()
        }
    }

    private var overviewSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Your work")
                .font(.headline)
                .foregroundStyle(GummfitTheme.textPrimary)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                creatorMetric("Offers", value: "\(vm.offersNeedingResponse.count)", detail: "need a response", icon: "envelope.badge")
                creatorMetric("Active deals", value: "\(vm.activeDeals.count)", detail: "in progress", icon: "sparkles")
                creatorMetric("Pending", value: Formatters.cents(vm.pendingEarnings), detail: "earnings", icon: "clock.badge.checkmark")
                creatorMetric("Portfolio", value: "\(vm.profile?.portfolio.count ?? 0)", detail: "pieces live", icon: "rectangle.stack")
            }

            Button { onSelect(.deals) } label: {
                Label("View all deals", systemImage: "arrow.right")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(GummfitTheme.accent)
            }
            .padding(.top, 2)
        }
        .gummfitCard()
    }

    private var profileSection: some View {
        Button { onSelect(.profile) } label: {
            HStack(spacing: 12) {
                Image(systemName: vm.profileIsReady ? "checkmark.seal.fill" : "person.crop.circle")
                    .font(.title2)
                    .foregroundStyle(vm.profileIsReady ? GummfitTheme.accent : GummfitTheme.warning)
                VStack(alignment: .leading, spacing: 3) {
                    Text(vm.profileIsReady ? "Your profile is ready" : "Make your profile work harder")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(GummfitTheme.textPrimary)
                    Text(vm.profileIsReady ? "Keep it current as your audience grows." : "A complete profile makes it easier for brands to choose you.")
                        .font(.caption)
                        .foregroundStyle(GummfitTheme.textDim)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(GummfitTheme.textDim)
            }
        }
        .buttonStyle(.plain)
        .gummfitCard()
    }

    private func dashboardAction(_ title: String, detail: String, icon: String, destination: CreatorTab) -> some View {
        Button { onSelect(destination) } label: {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .foregroundStyle(GummfitTheme.accent)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(GummfitTheme.textPrimary)
                    Text(detail).font(.caption).foregroundStyle(GummfitTheme.textDim).lineLimit(2)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption.bold()).foregroundStyle(GummfitTheme.textDim)
            }
        }
        .buttonStyle(.plain)
    }

    private func creatorMetric(_ title: String, value: String, detail: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Image(systemName: icon).foregroundStyle(GummfitTheme.accent)
            Text(value).font(.title3.bold()).foregroundStyle(GummfitTheme.textPrimary)
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textPrimary)
            Text(detail).font(.caption2).foregroundStyle(GummfitTheme.textDim)
        }
        .frame(maxWidth: .infinity, minHeight: 108, alignment: .leading)
        .padding(14)
        .background(GummfitTheme.surfaceRaised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
