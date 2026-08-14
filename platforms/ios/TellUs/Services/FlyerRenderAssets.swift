import UIKit

struct FlyerRenderAssets {
    let logo: UIImage?
    let stickers: [String: UIImage]

    static let bundled: FlyerRenderAssets = {
        let stickers = FlyerAssetCatalog.stickerImageNames.reduce(into: [String: UIImage]()) { result, item in
            if let image = UIImage(named: item.value) {
                result[item.key] = image
            }
        }
        return FlyerRenderAssets(logo: nil, stickers: stickers)
    }()

    func withLogo(_ image: UIImage?) -> FlyerRenderAssets {
        FlyerRenderAssets(logo: image, stickers: stickers)
    }
}
