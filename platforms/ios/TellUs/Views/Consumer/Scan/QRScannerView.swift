import SwiftUI
import VisionKit

/// Wraps VisionKit's DataScannerViewController for QR-only recognition.
/// Availability-gated by the caller (`DataScannerViewController.isSupported
/// && .isAvailable`) — simulator and pre-A12 hardware never have it, so
/// ScanView always shows a manual paste field alongside this.
struct QRScannerView: UIViewControllerRepresentable {
    /// Caller drives re-arming: false while an intake flow launched from a
    /// scan is on screen, true again once it pops back to the scan root —
    /// otherwise the single-shot `didFire` latch left a dead camera preview
    /// after the first successful scan.
    var isActive: Bool
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

    func updateUIViewController(_ uiViewController: DataScannerViewController, context: Context) {
        if isActive {
            context.coordinator.didFire = false
            if !uiViewController.isScanning { try? uiViewController.startScanning() }
        } else if uiViewController.isScanning {
            uiViewController.stopScanning()
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onCode: (String) -> Void
        var didFire = false
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !didFire, case let .barcode(barcode) = addedItems.first, let value = barcode.payloadStringValue else { return }
            didFire = true
            dataScanner.stopScanning()
            onCode(value)
        }
    }
}
