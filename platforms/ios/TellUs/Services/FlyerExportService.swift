import Foundation
import UIKit

enum FlyerExportDPI: String, CaseIterable, Identifiable {
    case dpi150 = "150dpi"
    case dpi300 = "300dpi"

    var id: String { rawValue }
    var pixelMultiplier: CGFloat { self == .dpi150 ? 1 : 2 }
    var label: String { self == .dpi150 ? "PNG 150dpi" : "PNG 300dpi" }
}

enum FlyerExportError: Error, LocalizedError, Equatable {
    case missingClaimURL
    case couldNotWriteFile

    var errorDescription: String? {
        switch self {
        case .missingClaimURL: return "This campaign does not have a claim link yet."
        case .couldNotWriteFile: return "Could not create the flyer image."
        }
    }
}

enum FlyerExportService {
    static func writePNG(
        design: FlyerDesign,
        claimURL: String,
        assets: FlyerRenderAssets,
        dpi: FlyerExportDPI,
        directory: URL = FileManager.default.temporaryDirectory
    ) throws -> URL {
        guard !claimURL.isEmpty else { throw FlyerExportError.missingClaimURL }
        let image = try FlyerRenderer.image(
            design: design,
            claimURL: claimURL,
            assets: assets,
            pixelMultiplier: dpi.pixelMultiplier
        )
        guard let data = image.pngData() else { throw FlyerExportError.couldNotWriteFile }
        let url = directory.appendingPathComponent("flyer-\(design.artboard.preset)-\(dpi.rawValue).png")
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            throw FlyerExportError.couldNotWriteFile
        }
    }
}
