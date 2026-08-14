import UIKit

struct FlyerRenderAssets {
    let logo: UIImage?
    let stickers: [String: UIImage]
    let images: [String: UIImage]

    static let bundled: FlyerRenderAssets = {
        let stickers = FlyerAssetCatalog.stickerImageNames.reduce(into: [String: UIImage]()) { result, item in
            if let image = UIImage(named: item.value) {
                result[item.key] = image
            }
        }
        return FlyerRenderAssets(logo: nil, stickers: stickers, images: [:])
    }()

    func withLogo(_ image: UIImage?) -> FlyerRenderAssets {
        FlyerRenderAssets(logo: image, stickers: stickers, images: images)
    }

    func withImages(_ images: [String: UIImage]) -> FlyerRenderAssets {
        FlyerRenderAssets(logo: logo, stickers: stickers, images: images)
    }
}
