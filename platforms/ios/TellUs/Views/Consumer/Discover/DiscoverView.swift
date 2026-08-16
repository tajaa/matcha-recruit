import SwiftUI

/// New Home tab root. Unlike the old PlacesView search box, the nearby list
/// renders with NO typing required — that's the whole point of Discover.
struct DiscoverView: View {
    @State private var vm = DiscoverViewModel()

    var body: some View {
        List {
            Section {
                TextField("Search nearby…", text: $vm.query)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
            }
            .listRowBackground(TU.inkRaised)

            if vm.locationDenied {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Showing results for your city").font(.interSubheadline)
                        NavigationLink("Set your city in Settings") { ConsumerSettingsView() }
                            .font(.interFootnote)
                    }
                    .padding(.vertical, 4)
                }
                .listRowBackground(TU.inkRaised)
            }

            if vm.entries.isEmpty && !vm.isLoading {
                EmptyState(icon: "mappin.slash", title: "No businesses found",
                           hint: "Try a different search or check back soon.")
                    .listRowBackground(TU.inkRaised)
            } else {
                Section {
                    ForEach(vm.entries) { entry in
                        DiscoverCard(
                            entry: entry,
                            onFollow: { Task { await vm.toggleFollow(entry) } },
                            onAddToTellUs: { Task { _ = await vm.addToTellUs(entry) } }
                        )
                        .task {
                            if entry.id == vm.entries.last?.id { await vm.loadMore() }
                        }
                    }
                }
                .listRowBackground(TU.inkRaised)

                if vm.showsGoogleAttribution {
                    Text("Some results from Google")
                        .font(.interCaption2).foregroundStyle(TU.textDim)
                        .listRowBackground(Color.clear)
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Discover")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { RewardsHomeView() } label: {
                    if let balance = PointsStore.shared.balance {
                        PointsPill(points: balance.points_balance)
                    } else {
                        Image(systemName: "sparkles")
                    }
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { NotificationsView() } label: {
                    Image(systemName: "bell")
                }
            }
        }
        .task { await vm.onAppear() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
