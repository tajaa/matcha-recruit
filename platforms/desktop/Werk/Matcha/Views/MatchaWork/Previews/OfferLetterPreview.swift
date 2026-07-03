import SwiftUI
import PDFKit

struct OfferLetterPreview: View {
    let pdfData: Data?

    var body: some View {
        if let data = pdfData {
            PDFKitView(data: data)
        } else {
            EmptyPreviewView(message: "No document yet", icon: "doc.text")
        }
    }
}

struct PDFKitView: NSViewRepresentable {
    let data: Data

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.backgroundColor = NSColor(Color.zinc900)
        if let document = PDFDocument(data: data) {
            pdfView.document = document
            context.coordinator.loadedDataID = dataIdentity(data)
        }
        return pdfView
    }

    func updateNSView(_ nsView: PDFView, context: Context) {
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
