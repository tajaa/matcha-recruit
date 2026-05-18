import SwiftUI
import PDFKit
import AppKit

/// Modal preview for task / project attachments. Images render inline via
/// `AsyncImage`, PDFs via the existing `PDFKitView` (defined in
/// `OfferLetterPreview.swift`), and everything else shows metadata plus an
/// "Open in default app" fallback. Used by `KanbanBoardView` and
/// `ProjectFilesView` so clicking an attachment no longer punts to Safari.
struct AttachmentPreviewSheet: View {
    let file: MWProjectFile
    @Environment(\.dismiss) private var dismiss
    @State private var pdfData: Data?
    @State private var loadError: String?

    private var isPDF: Bool {
        if let ct = file.contentType, ct.lowercased() == "application/pdf" { return true }
        return (file.filename as NSString).pathExtension.lowercased() == "pdf"
    }

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button(action: { dismiss() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .help("Close")

                Spacer()

                Text(file.filename)
                    .font(.system(size: 13, weight: .medium))
                    .lineLimit(1)
                    .truncationMode(.middle)

                Spacer()

                if let url = URL(string: file.storageUrl) {
                    Button(action: { NSWorkspace.shared.open(url) }) {
                        Image(systemName: "arrow.up.right.square")
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .help("Open in default app")
                }
            }
            .padding(12)

            Divider()

            content
                .frame(minWidth: 600, minHeight: 480)
        }
    }

    @ViewBuilder
    private var content: some View {
        if file.isImage, let url = URL(string: file.storageUrl) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    ProgressView()
                case .success(let img):
                    img
                        .resizable()
                        .scaledToFit()
                case .failure:
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 32))
                            .foregroundColor(.secondary)
                        Text("Failed to load image").foregroundColor(.secondary)
                    }
                @unknown default:
                    EmptyView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(16)
        } else if isPDF {
            if let data = pdfData {
                PDFKitView(data: data)
            } else if let err = loadError {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.secondary)
                    Text(err).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .task { await loadPDF() }
            }
        } else {
            VStack(spacing: 14) {
                Image(systemName: "doc")
                    .font(.system(size: 56, weight: .light))
                    .foregroundColor(.secondary)
                Text(file.filename)
                    .font(.headline)
                    .multilineTextAlignment(.center)
                Text(sizeLabel)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                if let url = URL(string: file.storageUrl) {
                    Button("Open in default app") {
                        NSWorkspace.shared.open(url)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(32)
        }
    }

    private func loadPDF() async {
        guard let url = URL(string: file.storageUrl) else {
            await MainActor.run { loadError = "Invalid URL" }
            return
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            await MainActor.run { pdfData = data }
        } catch {
            await MainActor.run {
                loadError = "Failed to load PDF: \(error.localizedDescription)"
            }
        }
    }
}
