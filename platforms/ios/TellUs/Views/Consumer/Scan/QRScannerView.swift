import SwiftUI
import VisionKit

/// Wraps VisionKit's DataScannerViewController for QR-only recognition.
/// Availability-gated by the caller (`DataScannerViewController.isSupported
/// && .isAvailable`) — simulator and pre-A12 hardware never have it, so
/// ScanView always shows a manual paste field alongside this.
struct QRScannerView: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let controller = DataScannerViewController(
            recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced,
            isHighFrameRateTrackingEnabled: false,
            isPinchToZoomEnabled: false,
            isGuidanceEnabled: true,
            isHighlightingEnabled: true
        )
        controller.delegate = context.coordinator
        try? controller.startScanning()
        return controller
    }

    func updateUIViewController(_ uiViewController: DataScannerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onCode: (String) -> Void
        private var didFire = false
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !didFire, case let .barcode(barcode) = addedItems.first, let value = barcode.payloadStringValue else { return }
            didFire = true
            dataScanner.stopScanning()
            onCode(value)
        }
    }
}
