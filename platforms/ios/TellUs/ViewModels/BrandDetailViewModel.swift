import Foundation

@MainActor
@Observable
final class BrandDetailViewModel: LoadableVM {
    let slug: String
    var isLoading = false
    var error: String?
    var page: TellusPublicBrandPage?
    var followed = false
    var showIntake = false
    var showBoard = false
    var shareItem: DiscoverShareItem?

    init(slug: String) {
        self.slug = slug
    }

    func load() async {
        await withLoad {
            let page = try await PublicBrandService.shared.brandDetail(slug: self.slug)
            self.page = page
            self.followed = page.followed
        }
    }

    func toggleFollow() async {
        let was = followed
        followed.toggle()
        do {
            if was {
                try await PlacesService.shared.unfollow(slug: slug)
            } else {
                _ = try await PlacesService.shared.follow(slug: slug)
            }
        } catch {
            followed = was
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    func invite() async {
        guard page != nil else { return }
        do {
            let resp = try await DiscoverService.shared.invite(slug: slug)
            // TellusPublicBrandPage has no per-field mutation (all `let`,
            // custom decoder) — simplest correct update is a re-fetch rather
            // than hand-rolling a copy-with. Low-frequency action, so the
            // extra round trip is not a UX concern.
            await load()
            if let url = URL(string: APIClient.shared.webOrigin + resp.share_url) {
                shareItem = DiscoverShareItem(url: url, text: resp.share_text)
            }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }
}
