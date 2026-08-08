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
    @State private var showDirectory = false
    @State private var showCreateSite = false
    @State private var declineTarget: CappeRequestSummary?
    @State private var declineReason = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                ErrorBanner(message: vm.error)
                siteCard
                pendingRequestsSection
                readinessSection
                publishButton
            }
            .padding()
        }
        .background(Color(GummfitTheme.background).ignoresSafeArea())
        .navigationTitle(site.name)
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
        .alert("Decline request", isPresented: Binding(get: { declineTarget != nil }, set: { if !$0 { declineTarget = nil } })) {
            TextField("Reason (optional)", text: $declineReason)
            Button("Decline", role: .destructive) {
                if let target = declineTarget {
                    Task { await requestsVM.decline(siteId: site.id, target, reason: declineReason.isEmpty ? nil : declineReason) }
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .task(id: site.id) {
            vm.reset()
            async let readiness: Void = vm.loadReadiness(siteId: site.id)
            async let requests: Void = requestsVM.load(siteId: site.id)
            _ = await (readiness, requests)
        }
        .refreshable {
            async let sites: Void = appState.loadSites()
            async let readiness: Void = vm.loadReadiness(siteId: site.id)
            async let requests: Void = requestsVM.load(siteId: site.id)
            _ = await (sites, readiness, requests)
        }
    }

    /// Empty state renders nothing — no "no requests" clutter on a fresh site.
    @ViewBuilder
    private var pendingRequestsSection: some View {
        if !requestsVM.requests.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Needs your review").font(.subheadline.bold())
                ForEach(requestsVM.requests) { request in
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(request.customer_name ?? request.customer_email ?? request.title)
                                .font(.subheadline)
                            Text(request.title).font(.caption).foregroundStyle(GummfitTheme.textDim)
                        }
                        Spacer()
                        Button("Accept") { Task { await requestsVM.accept(siteId: site.id, request) } }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                        Button("Decline") {
                            declineTarget = request
                            declineReason = ""
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
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
            Image(systemName: "chevron.down.circle")
        }
    }

    private var siteCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(site.name).font(.headline)
                Spacer()
                statusPill
            }
            if let urlString = site.publicURLString, let url = SafeURL.validated(urlString) {
                Link(urlString, destination: url)
                    .font(.footnote)
                    .lineLimit(1)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private var statusPill: some View {
        Text(site.status.rawValue.capitalized)
            .font(.caption.bold())
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(site.status == .published ? GummfitTheme.accent.opacity(0.2) : Color.gray.opacity(0.2), in: Capsule())
            .foregroundStyle(site.status == .published ? GummfitTheme.accent : GummfitTheme.textDim)
    }

    @ViewBuilder
    private var readinessSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Launch checklist").font(.subheadline.bold())
            if vm.isLoading && vm.readiness == nil {
                ProgressView().frame(maxWidth: .infinity)
            } else if let readiness = vm.readiness {
                ForEach(readiness.items) { item in
                    readinessRow(item)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func readinessRow(_ item: CappeReadinessItem) -> some View {
        let blocked = vm.publishBlockedKeys?.contains(item.key) ?? false
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: item.done ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(item.done ? GummfitTheme.accent : (blocked ? .red : GummfitTheme.textDim))
            VStack(alignment: .leading, spacing: 2) {
                Text(item.label).font(.subheadline)
                Text(item.hint).font(.caption).foregroundStyle(GummfitTheme.textDim)
            }
            Spacer()
        }
    }

    private var publishButton: some View {
        Button {
            Task { await vm.publish(site: site, appState: appState) }
        } label: {
            HStack {
                if vm.isPublishing { ProgressView().tint(.white) }
                Text(site.status == .published ? "Published" : "Publish")
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .disabled(vm.isPublishing || site.status == .published)
    }
}
