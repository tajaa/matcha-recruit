import CoreImage.CIFilterBuiltins
import SwiftUI

/// Renders a QR code for `content` (a feedback-link URL). Used by brand
/// Stores & QR management to show/share/copy a link's intake QR.
struct QRCodeView: View {
    let content: String

    private var image: Image {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(content.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage else { return Image(systemName: "qrcode") }
        let scaled = output.transformed(by: CGAffineTransform(scaleX: 8, y: 8))
        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else {
            return Image(systemName: "qrcode")
        }
        return Image(decorative: cgImage, scale: 1).interpolation(.none)
    }

    var body: some View {
        image
            .resizable()
            .scaledToFit()
    }
}
