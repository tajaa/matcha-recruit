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
}
