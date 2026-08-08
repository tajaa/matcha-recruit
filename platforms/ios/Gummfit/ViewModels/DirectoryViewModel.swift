import Foundation
import Observation

/// Backs DirectorySheet. v1 only surfaces the `listed` toggle plus the
/// server-computed visibility/blocked state — full category/tag/blurb
/// editing is a later polish pass (the server already accepts partial PATCHes
/// for it, so this is additive, not a redesign).
@MainActor
@Observable
final class DirectoryViewModel: LoadableVM {
    var listing: CappeDirectoryListing?
    var isLoading = false
    var error: String?
    var isSaving = false

    func load(siteId: String) async {
        await withLoad {
            self.listing = try await SitesService.shared.directory(siteId: siteId)
        }
    }

    func toggleListed(siteId: String) async {
        guard let listing else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            self.listing = try await SitesService.shared.updateDirectory(
                siteId: siteId,
                CappeDirectoryListingUpdate(listed: !listing.listed)
            )
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
