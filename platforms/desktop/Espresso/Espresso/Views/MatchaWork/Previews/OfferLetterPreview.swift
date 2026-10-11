import SwiftUI
import PDFKit

struct OfferLetterPreview: View {
    @Environment(AppState.self) private var appState
    let pdfData: Data?

    var body: some View {
        if let data = pdfData {
            // Pages float on the canvas's own background, with PDFKit's page
            // shadows, instead of on a fixed dark slab.
            PDFKitView(data: data, background: NSColor(appState.themeBg))
        } else {
            EmptyPreviewView(message: "No document yet", icon: "doc.text")
        }
    }
}

struct PDFKitView: NSViewRepresentable {
    let data: Data
    var background: NSColor = NSColor(Color.zinc900)

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.pageShadowsEnabled = true
        pdfView.pageBreakMargins = NSEdgeInsets(top: 18, left: 22, bottom: 18, right: 22)
        pdfView.backgroundColor = background
        if let document = PDFDocument(data: data) {
            pdfView.document = document
            context.coordinator.loadedDataID = dataIdentity(data)
        }
        return pdfView
    }

    func updateNSView(_ nsView: PDFView, context: Context) {
        if nsView.backgroundColor != background { nsView.backgroundColor = background }
        let newID = dataIdentity(data)
        guard newID != context.coordinator.loadedDataID else { return }
        if let document = PDFDocument(data: data) {
            nsView.document = document
            context.coordinator.loadedDataID = newID
        }
    }

    private func dataIdentity(_ data: Data) -> String {
        "\(data.count)-\(data.prefix(64).hashValue)"
    }

    class Coordinator {
        var loadedDataID: String?
    }
}
