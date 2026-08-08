import Foundation
import Observation
import PhotosUI
import SwiftUI

@MainActor
@Observable
final class BrandSettingsViewModel: LoadableVM {
    var brand: Brand?
    var prompts: [BrandPrompt] = []
    var isLoading = false
    var error: String?
    var savedBrand = false
    var savedPrompts = false

    func load() async {
        await withLoad {
            async let b = BrandAdminService.shared.brand()
            async let p = BrandAdminService.shared.prompts()
            brand = try await b
            prompts = try await p
        }
    }

    func saveBrand(name: String, rewardMode: RewardMode) async {
        savedBrand = false
        await withLoad {
            brand = try await BrandAdminService.shared.updateBrand(BrandUpdate(name: name, reward_mode: rewardMode.rawValue))
            savedBrand = true
        }
    }

    /// ≤2MB, png/jpeg/webp — matches the server's accepted content types.
    func uploadLogo(item: PhotosPickerItem) async {
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else { return }
            guard data.count <= 2_000_000 else {
                error = "Logo must be 2 MB or smaller."
                return
            }
            let utType = item.supportedContentTypes.first
            let mime = utType?.preferredMIMEType ?? "image/jpeg"
            guard ["image/png", "image/jpeg", "image/webp"].contains(mime) else {
                error = "Logo must be PNG, JPEG, or WebP."
                return
            }
            await withLoad {
                brand = try await BrandAdminService.shared.uploadLogo(data: data, mimeType: mime, filename: "logo")
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func removeLogo() async {
        await withLoad {
            brand = try await BrandAdminService.shared.deleteLogo()
        }
    }

    /// PUT replaces the whole set — array order becomes position, ≤5.
    func savePrompts(_ texts: [String]) async {
        savedPrompts = false
        let trimmed = texts.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        await withLoad {
            prompts = try await BrandAdminService.shared.setPrompts(Array(trimmed.prefix(5)))
            savedPrompts = true
        }
    }
}
