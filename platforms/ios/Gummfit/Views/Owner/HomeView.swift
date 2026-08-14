import SwiftUI

/// Owner's Home tab: site card + readiness checklist + publish + site
/// switcher. `site` is read fresh from `appState.activeSite` by the caller
/// (OwnerTabView), which pins `.id(site.id)` so this view is genuinely
/// recreated — not just re-rendered — on a site switch; `.task(id:)` below
/// also resets the VM as a belt-and-braces guard against that identity ever
/// being dropped.
struct HomeView: View {
    let site: CappeSite

    @Environment(AppState.self) private var appState
    @State private var vm = HomeViewModel()
    @State private var requestsVM = RequestsQueueViewModel()
    @State private var dashboard = OwnerDashboardViewModel()
    @State private var showDirectory = false
    @State private var showCreateSite = false
    @State private var declineTarget: CappeRequestSummary?
    @State private var declineReason = ""
    @State private var showDecline = false
    @State private var showSetupProgress = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ErrorBanner(message: vm.error)
                siteCard
                pendingRequestsSection
                if site.status == .published {
                    operatingDashboard
                    publishedReadinessSection
                } else {
                    readinessSection
                    publishButton
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
            .padding(.bottom, 28)
        }
        .navigationTitle("Overview")
        .navigationBarTitleDisplayMode(.inline)
        .gummfitScreenChrome()
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                siteSwitcherMenu
            }
        }
        .sheet(isPresented: $showDirectory) {
            DirectorySheet(siteId: site.id)
        }
        .sheet(isPresented: $showCreateSite) {
            NavigationStack { CreateSiteView() }
        }
        .alert("Decline request", isPresented: $showDecline, presenting: declineTarget) { target in
            TextField("Reason (optional)", text: $declineReason)
            Button("Decline", role: .destructive) {
                Task { await requestsVM.decline(siteId: site.id, target, reason: declineReason.isEmpty ? nil : declineReason) }
            }
            Button("Cancel", role: .cancel) {}
        }
        .task(id: site.id) {
            vm.reset()
            dashboard.reset()
            async let readiness: Void = vm.loadReadiness(siteId: site.id)
            async let requests: Void = requestsVM.load(siteId: site.id)
            async let operations: Void = dashboard.load(siteId: site.id)
            _ = await (readiness, requests, operations)
        }
        .refreshable {
            async let sites: Void = appState.loadSites()
            async let readiness: Void = vm.loadReadiness(siteId: site.id)
            async let requests: Void = requestsVM.load(siteId: site.id)
            async let operations: Void = dashboard.load(siteId: site.id)
            _ = await (sites, readiness, requests, operations)
        }
    }

    @ViewBuilder
    private var operatingDashboard: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text(appState.account?.account_type == .business ? "Run your business" : "Your site today")
                    .font(.headline)
                    .foregroundStyle(GummfitTheme.textPrimary)
                Text("A live view of the work that keeps your site moving.")
                    .font(.subheadline)
                    .foregroundStyle(GummfitTheme.textDim)
            }

            if dashboard.isLoading && dashboard.orders.isEmpty {
                ProgressView()
                    .tint(GummfitTheme.accent)
                    .frame(maxWidth: .infinity, minHeight: 104)
            } else {
                attentionItems
                operationalMetrics
                quickActions
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var attentionItems: some View {
        if !dashboard.openOrders.isEmpty || !dashboard.upcomingBookings.isEmpty || dashboard.unreadMessages > 0 || !dashboard.lowStockProducts.isEmpty || dashboard.pendingReviews > 0 {
            VStack(alignment: .leading, spacing: 10) {
                Label("Needs your attention", systemImage: "exclamationmark.circle.fill")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(GummfitTheme.warning)

                if !dashboard.openOrders.isEmpty {
                    dashboardAction(
                        "Fulfill (dashboard.openOrders.count) order\(dashboard.openOrders.count == 1 ? "" : "s")",
                        detail: "Paid or awaiting your approval",
                        icon: "bag.badge.plus",
                        destination: { OrderListView(site: site) }
                    )
                }
                if !dashboard.upcomingBookings.isEmpty {
                    dashboardAction(
                        "Check (dashboard.upcomingBookings.count) upcoming booking\(dashboard.upcomingBookings.count == 1 ? "" : "s")",
                        detail: "Confirm details and keep your schedule current",
                        icon: "calendar.badge.clock",
                        destination: { BookingListView(site: site) }
                    )
                }
                if dashboard.unreadMessages > 0 {
                    dashboardAction(
                        "Reply to (dashboard.unreadMessages) message\(dashboard.unreadMessages == 1 ? "" : "s")",
                        detail: "Customers are waiting to hear from you",
                        icon: "envelope.badge.fill",
                        destination: { ThreadListView(site: site) }
                    )
                }
                if !dashboard.lowStockProducts.isEmpty {
                    dashboardAction(
                        "Restock (dashboard.lowStockProducts.count) item\(dashboard.lowStockProducts.count == 1 ? "" : "s")",
                        detail: "At or below your stock threshold",
                        icon: "shippingbox.fill",
                        destination: { ProductListView(site: site) }
                    )
                }
                if dashboard.pendingReviews > 0 {
                    dashboardAction(
                        "Moderate (dashboard.pendingReviews) review\(dashboard.pendingReviews == 1 ? "" : "s")",
                        detail: "Keep new feedback visible and current",
                        icon: "star.bubble.fill",
                        destination: { ReviewsView(site: site) }
                    )
                }
            }
            .gummfitCard()
        }
    }

    private var operationalMetrics: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("At a glance")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(GummfitTheme.textPrimary)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                NavigationLink { OrderListView(site: site) } label: {
                    dashboardMetric("Orders", value: "\(dashboard.openOrders.count)", detail: "to review or fulfill", icon: "bag")
                }
                NavigationLink { BookingListView(site: site) } label: {
                    dashboardMetric("Bookings", value: "\(dashboard.upcomingBookings.count)", detail: "upcoming", icon: "calendar")
                }
                NavigationLink { ThreadListView(site: site) } label: {
                    dashboardMetric("Inbox", value: "\(dashboard.unreadMessages)", detail: "unread messages", icon: "envelope")
                }
                NavigationLink { ProductListView(site: site) } label: {
                    dashboardMetric("Catalog", value: "\(dashboard.products.count)", detail: dashboard.lowStockProducts.isEmpty ? "items live" : "\(dashboard.lowStockProducts.count) low in stock", icon: "square.grid.2x2")
                }
            }
        }
        .gummfitCard()
    }

    private var quickActions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Keep building")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(GummfitTheme.textPrimary)
            HStack(spacing: 10) {
                dashboardShortcut("Add product", icon: "plus.circle.fill", destination: { ProductListView(site: site) })
                dashboardShortcut("View sales", icon: "chart.line.uptrend.xyaxis", destination: { OrderListView(site: site) })
                if site.is_multi_location {
                    dashboardShortcut("Locations", icon: "mappin.and.ellipse", destination: { LocationsStaffView(site: site) })
                }
            }
        }
        .gummfitCard()
    }

    @ViewBuilder
    private var publishedReadinessSection: some View {
        if !readinessIsComplete {
            DisclosureGroup(isExpanded: $showSetupProgress) {
                VStack(alignment: .leading, spacing: 12) {
                    if let readiness = vm.readiness {
                        readinessProgress(readiness)
                        ForEach(Array(readiness.items.enumerated()), id: \.element.id) { index, item in
                            readinessRow(item)
                            if index < readiness.items.count - 1 {
                                Divider().overlay(GummfitTheme.border)
                            }
                        }
                    }
                }
                .padding(.top, 12)
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Finish setting up")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(GummfitTheme.textPrimary)
                    Text(readinessSubtitle)
                        .font(.caption)
                        .foregroundStyle(GummfitTheme.textDim)
                }
            }
            .tint(GummfitTheme.accent)
            .gummfitCard()
        }
    }

    private func dashboardAction<Destination: View>(_ title: String, detail: String, icon: String, @ViewBuilder destination: @escaping () -> Destination) -> some View {
        NavigationLink(destination: destination) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(GummfitTheme.accent)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(GummfitTheme.textPrimary)
                    Text(detail).font(.caption).foregroundStyle(GummfitTheme.textDim)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption.bold()).foregroundStyle(GummfitTheme.textDim)
            }
        }
        .buttonStyle(.plain)
    }

    private func dashboardMetric(_ title: String, value: String, detail: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Image(systemName: icon).foregroundStyle(GummfitTheme.accent)
            Text(value).font(.title3.bold()).foregroundStyle(GummfitTheme.textPrimary)
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textPrimary)
            Text(detail).font(.caption2).foregroundStyle(GummfitTheme.textDim).lineLimit(1)
        }
        .frame(maxWidth: .infinity, minHeight: 106, alignment: .leading)
        .padding(14)
        .background(GummfitTheme.surfaceRaised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func dashboardShortcut<Destination: View>(_ title: String, icon: String, @ViewBuilder destination: @escaping () -> Destination) -> some View {
        NavigationLink(destination: destination) {
            VStack(spacing: 7) {
                Image(systemName: icon).font(.title3).foregroundStyle(GummfitTheme.accent)
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textPrimary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, minHeight: 62)
            .background(GummfitTheme.surfaceRaised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    /// Empty state renders nothing — no "no requests" clutter on a fresh site.
    @ViewBuilder
    private var pendingRequestsSection: some View {
        if !requestsVM.requests.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Label("Needs your review", systemImage: "bell.badge.fill")
                    .font(.headline)
                    .foregroundStyle(GummfitTheme.textPrimary)
                ForEach(requestsVM.requests) { request in
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(request.customer_name ?? request.customer_email ?? request.title)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(GummfitTheme.textPrimary)
                            Text(request.title).font(.caption).foregroundStyle(GummfitTheme.textDim)
                        }
                        Spacer()
                        Button("Accept") { Task { await requestsVM.accept(siteId: site.id, request) } }
                            .buttonStyle(.gummfitPrimary)
                            .controlSize(.small)
                        Button("Decline") {
                            declineTarget = request
                            declineReason = ""
                            showDecline = true
                        }
                        .buttonStyle(.gummfitSecondary)
                        .controlSize(.small)
                    }
                    .padding(.vertical, 4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .gummfitCard()
        }
    }

    private var siteSwitcherMenu: some View {
        Menu {
            ForEach(appState.sites) { s in
                Button {
                    appState.selectSite(s)
                } label: {
                    if s.id == site.id {
                        Label(s.name, systemImage: "checkmark")
                    } else {
                        Text(s.name)
                    }
                }
            }
            Divider()
            Button("New site") { showCreateSite = true }
            Button("Discover listing") { showDirectory = true }
        } label: {
            Image(systemName: "building.2.crop.circle.fill")
                .font(.title3)
                .foregroundStyle(GummfitTheme.textPrimary)
        }
    }

    private var siteCard: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 13) {
                Image(systemName: "storefront.fill")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(GummfitTheme.background)
                    .frame(width: 50, height: 50)
                    .background(GummfitTheme.accent, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                VStack(alignment: .leading, spacing: 5) {
                    Text("YOUR BUSINESS")
                        .font(.caption2.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(GummfitTheme.textDim)
                    Text(site.name)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(GummfitTheme.textPrimary)
                        .lineLimit(2)
                }
                Spacer()
                statusPill
            }
            if let urlString = site.publicURLString, let url = SafeURL.validated(urlString) {
                Link(destination: url) {
                    Label("Visit live site", systemImage: "arrow.up.right")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(GummfitTheme.accent)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background {
            LinearGradient(
                colors: [GummfitTheme.accentDeep.opacity(0.9), GummfitTheme.surface],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        }
        .overlay {
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(GummfitTheme.accent.opacity(0.26), lineWidth: 1)
        }
    }

    private var statusPill: some View {
        GummfitStatusPill(status: site.status.rawValue)
    }

    @ViewBuilder
    private var readinessSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Launch readiness")
                        .font(.headline)
                        .foregroundStyle(GummfitTheme.textPrimary)
                    Text(readinessSubtitle)
                        .font(.subheadline)
                        .foregroundStyle(GummfitTheme.textDim)
                }
                Spacer()
                Image(systemName: readinessIsComplete ? "checkmark.seal.fill" : "flag.checkered")
                    .font(.title3)
                    .foregroundStyle(readinessIsComplete ? GummfitTheme.accent : GummfitTheme.warning)
            }

            if let readiness = vm.readiness {
                readinessProgress(readiness)
            }

            if vm.isLoading && vm.readiness == nil {
                ProgressView().tint(GummfitTheme.accent).frame(maxWidth: .infinity)
            } else if let readiness = vm.readiness {
                ForEach(Array(readiness.items.enumerated()), id: \.element.id) { index, item in
                    readinessRow(item)
                    if index < readiness.items.count - 1 {
                        Divider().overlay(GummfitTheme.border)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gummfitCard()
    }

    private func readinessRow(_ item: CappeReadinessItem) -> some View {
        let blocked = vm.publishBlockedKeys?.contains(item.key) ?? false
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.done ? "checkmark.circle.fill" : "circle")
                .font(.title3)
                .foregroundStyle(item.done ? GummfitTheme.accent : (blocked ? .red : GummfitTheme.textDim))
            VStack(alignment: .leading, spacing: 2) {
                Text(item.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(GummfitTheme.textPrimary)
                Text(item.hint)
                    .font(.caption)
                    .foregroundStyle(GummfitTheme.textDim)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
        }
    }

    private var publishButton: some View {
        Button {
            Task { await vm.publish(site: site, appState: appState) }
        } label: {
            HStack {
                if vm.isPublishing {
                    ProgressView().tint(GummfitTheme.background)
                } else {
                    Image(systemName: site.status == .published ? "checkmark.circle.fill" : "paperplane.fill")
                }
                Text(site.status == .published ? "Your site is live" : "Publish site")
            }
            .font(.headline)
            .foregroundStyle(GummfitTheme.background)
            .frame(height: 54)
            .frame(maxWidth: .infinity)
        }
        .background(GummfitTheme.accent, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
        .opacity(site.status == .published ? 0.58 : 1)
        .disabled(vm.isPublishing || site.status == .published)
    }

    private var readinessSubtitle: String {
        guard let readiness = vm.readiness else { return "Checking your setup…" }
        let complete = readiness.items.filter(\.done).count
        return readiness.ready ? "Everything is ready to go" : "\(complete) of \(readiness.items.count) essentials complete"
    }

    private var readinessIsComplete: Bool {
        vm.readiness?.ready ?? false
    }

    private func readinessProgress(_ readiness: CappeReadiness) -> some View {
        let total = max(readiness.items.count, 1)
        let completed = readiness.items.filter(\.done).count
        let progress = Double(completed) / Double(total)

        return ProgressView(value: progress)
            .tint(GummfitTheme.accent)
            .background(GummfitTheme.backgroundRaised, in: Capsule())
    }
}
