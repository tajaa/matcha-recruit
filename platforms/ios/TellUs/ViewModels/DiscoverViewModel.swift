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
    var shareItem: DiscoverShareItem?

    private var coordinate: (lat: Double, lng: Double)?
    private var nextOffset: Int?
    private var searchTask: Task<Void, Never>?
    private var isLoadingMore = false
    // Bumped before every load()/loadMore() request; a response is only
    // applied if this hasn't moved on since — guards a debounced load()
    // landing after (or racing) an in-flight loadMore(), and vice versa.
    private var generation = 0

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
        generation += 1
        let myGeneration = generation
        await withLoad {
            let page = try await DiscoverService.shared.discover(
                lat: self.coordinate?.lat, lng: self.coordinate?.lng,
                q: self.query.isEmpty ? nil : self.query, city: nil, state: nil,
                offset: 0
            )
            guard myGeneration == self.generation else { return }
            self.entries = page.entries
            self.nextOffset = page.next_offset
            self.showsGoogleAttribution = page.google_attribution
        }
    }

    func loadMore() async {
        guard let offset = nextOffset, !isLoadingMore else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        let myGeneration = generation
        do {
            let page = try await DiscoverService.shared.discover(
                lat: coordinate?.lat, lng: coordinate?.lng,
                q: query.isEmpty ? nil : query, city: nil, state: nil,
                offset: offset
            )
            guard myGeneration == generation else { return }
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

    /// Google row: materialize first via the existing POST /places (through
    /// addToTellUs, which already advisory-locks and dedupes server-side),
    /// then invite the returned slug. No new dedupe logic needed here.
    func invite(_ entry: DiscoverEntry) async {
        var slug = entry.slug
        if slug == nil {
            slug = await addToTellUs(entry)?.slug
        }
        guard let slug, let idx = entries.firstIndex(where: { $0.id == entry.id }) else { return }

        entries[idx].invite_count += 1   // optimistic
        do {
            let resp = try await DiscoverService.shared.invite(slug: slug)
            entries[idx].invite_count = resp.invite_count   // authoritative
            // share_url from the server is a relative path (e.g. matches the
            // convention promo claim_url already uses) — prepend webOrigin so
            // the shared link is absolute outside the app.
            if let url = URL(string: APIClient.shared.webOrigin + resp.share_url) {
                shareItem = DiscoverShareItem(url: url, text: resp.share_text)
            }
        } catch {
            entries[idx].invite_count -= 1
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }
}
