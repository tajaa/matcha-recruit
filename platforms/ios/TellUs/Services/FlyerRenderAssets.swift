import UIKit

extension UIImage {
    /// Bakes EXIF orientation into the pixels. FlyerRenderer draws
    /// `.cgImage` directly (see drawUpright in FlyerRenderer.swift), which
    /// ignores `imageOrientation` — a camera-sourced logo/asset would
    /// otherwise render rotated independent of any layer rotation the user
    /// set. Cheap no-op when already upright.
    func normalizedUp() -> UIImage {
        guard imageOrientation != .up else { return self }
        let format = UIGraphicsImageRendererFormat()
        format.scale = scale
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

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
