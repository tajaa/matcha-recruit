import Foundation

@MainActor
@Observable
final class DiscoverViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var entries: [DiscoverEntry] = []
    var query = "" {
        didSet { if oldValue != query { queryChanged() } }
    }
    /// True once location has been resolved (granted or denied) so the view
    /// can distinguish "still figuring out location" from "denied, here's
    /// city-scoped results instead."
    var locationResolved = false
    var locationDenied = false
    var showsGoogleAttribution = false

    private var coordinate: (lat: Double, lng: Double)?
    private var nextOffset: Int?
    private var searchTask: Task<Void, Never>?

    func onAppear() async {
        guard !locationResolved else { return }
        let coord = await LocationService.shared.requestOnce()
        locationResolved = true
        if let coord {
            coordinate = (coord.latitude, coord.longitude)
            locationDenied = false
        } else {
            coordinate = nil
            locationDenied = true
        }
        await load()
    }

    func load() async {
        nextOffset = nil
        await withLoad {
            let page = try await DiscoverService.shared.discover(
                lat: self.coordinate?.lat, lng: self.coordinate?.lng,
                q: self.query.isEmpty ? nil : self.query, city: nil, state: nil,
                offset: 0
            )
            self.entries = page.entries
            self.nextOffset = page.next_offset
            self.showsGoogleAttribution = page.google_attribution
        }
    }

    func loadMore() async {
        guard let offset = nextOffset else { return }
        do {
            let page = try await DiscoverService.shared.discover(
                lat: coordinate?.lat, lng: coordinate?.lng,
                q: query.isEmpty ? nil : query, city: nil, state: nil,
                offset: offset
            )
            entries.append(contentsOf: page.entries)
            nextOffset = page.next_offset
        } catch {
            if error.isCancellation { return }
            // Silent — a failed "load more" shouldn't blank out what's
            // already on screen or steal the error banner from the initial load.
        }
    }

    /// Pure debounce/out-of-order guard, matching PlacesViewModel's shape —
    /// unlike PlacesViewModel, an empty query is a VALID state here (it's
    /// "nearby, unfiltered"), so there's no length gate.
    private func queryChanged() {
        searchTask?.cancel()
        searchTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 450_000_000)
            guard !Task.isCancelled else { return }
            await self?.load()
        }
    }

    func toggleFollow(_ entry: DiscoverEntry) async {
        guard let slug = entry.slug, let idx = entries.firstIndex(where: { $0.id == entry.id }) else { return }
        let wasFollowed = entries[idx].followed
        entries[idx].followed.toggle()
        do {
            if wasFollowed {
                try await PlacesService.shared.unfollow(slug: slug)
            } else {
                _ = try await PlacesService.shared.follow(slug: slug)
            }
        } catch {
            entries[idx].followed = wasFollowed
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    func addToTellUs(_ entry: DiscoverEntry) async -> PlaceCreateResponse? {
        guard entry.source == .google, let placeId = entry.google_place_id else { return nil }
        do {
            let req = PlaceCreateRequest(name: entry.name, google_place_id: placeId, session_token: nil)
            return try await PlacesService.shared.create(req)
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
            return nil
        }
    }
}
