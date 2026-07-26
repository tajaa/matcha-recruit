import SwiftUI
import PDFKit
import AppKit

/// Modal preview for task / project attachments. Images render inline via
/// `AsyncImage`, PDFs via the existing `PDFKitView` (defined in
/// `OfferLetterPreview.swift`), CSVs as an inline table, and other text-like
/// files (TXT/MD/JSON/log/…) as monospaced text. Everything else shows
/// metadata plus an "Open in default app" fallback. Used by `TaskViewerSheet`,
/// `TaskEditorSheet`, `ProjectFilesView`, and channel chat so clicking an
/// attachment no longer punts to the browser.
struct AttachmentPreviewSheet: View {
    let file: MWProjectFile
    @Environment(\.dismiss) private var dismiss

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

                VStack(spacing: 2) {
                    Text(file.filename)
                        .font(.system(size: 13, weight: .medium))
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(sizeLabel)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }

                Spacer()

                if SafeURL.isAllowed(file.storageUrl) {
                    Button(action: { SafeURL.open(file.storageUrl) }) {
                        Image(systemName: "arrow.up.right.square")
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .help("Open in default app")
                }
            }
            .padding(12)
            .background(Color.appBackground.opacity(0.95))

            Divider()

            AttachmentPreviewContent(file: file)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 900, minHeight: 700)
    }
}

/// The chrome-less preview body — shared by `AttachmentPreviewSheet` and the
/// split-pane file view (`AuxWindowTarget.file`), which supplies its own
/// header. No min-size frame here so it can live in a small bottom pane.
struct AttachmentPreviewContent: View {
    let file: MWProjectFile
    @State private var pdfData: Data?
    @State private var textContent: String?
    @State private var csvRows: [[String]]?
    @State private var loadError: String?

    /// Hard caps so a huge export can't lock the main thread on parse/render.
    private static let maxTextBytes = 512 * 1024
    private static let maxCSVRows = 500

    private var ext: String {
        (file.filename as NSString).pathExtension.lowercased()
    }

    private var isPDF: Bool {
        if let ct = file.contentType, ct.lowercased() == "application/pdf" { return true }
        return ext == "pdf"
    }

    private var isCSV: Bool {
        if let ct = file.contentType, ct.lowercased().contains("csv") { return true }
        return ext == "csv" || ext == "tsv"
    }

    private var isTextLike: Bool {
        let textExts: Set<String> = ["txt", "md", "markdown", "json", "log", "yml", "yaml", "xml"]
        if textExts.contains(ext) { return true }
        if let ct = file.contentType?.lowercased() {
            return ct.hasPrefix("text/") || ct == "application/json"
        }
        return false
    }

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        if file.isImage, let url = URL(string: file.storageUrl) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    ProgressView().tint(.white)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .success(let img):
                    img
                        .resizable()
                        .scaledToFit()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .failure:
                    centeredMessage(icon: "exclamationmark.triangle",
                                    text: "Failed to load image")
                @unknown default:
                    EmptyView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)
        } else if isPDF {
            if let data = pdfData {
                PDFKitView(data: data)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.black)
            } else if let err = loadError {
                centeredMessage(icon: "exclamationmark.triangle", text: err)
            } else {
                loadingView.task { await loadRemote { pdfData = $0 } }
            }
        } else if isCSV {
            if let rows = csvRows {
                csvTable(rows)
            } else if let err = loadError {
                centeredMessage(icon: "exclamationmark.triangle", text: err)
            } else {
                loadingView.task {
                    await loadRemote { data in
                        let text = Self.decodeText(data) ?? ""
                        csvRows = Self.parseCSV(
                            text,
                            separator: ext == "tsv" ? "\t" : ",",
                            maxRows: Self.maxCSVRows
                        )
                    }
                }
            }
        } else if isTextLike {
            if let text = textContent {
                ScrollView {
                    Text(text)
                        .font(.system(size: 12, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                        .padding(16)
                }
                .background(Color.appBackground)
            } else if let err = loadError {
                centeredMessage(icon: "exclamationmark.triangle", text: err)
            } else {
                loadingView.task {
                    await loadRemote { data in
                        let capped = data.prefix(Self.maxTextBytes)
                        var text = Self.decodeText(Data(capped)) ?? "Couldn't decode file as text."
                        if data.count > Self.maxTextBytes {
                            text += "\n\n… preview truncated (\(sizeLabel) total)"
                        }
                        textContent = text
                    }
                }
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
                if SafeURL.isAllowed(file.storageUrl) {
                    Button("Open in default app") {
                        SafeURL.open(file.storageUrl)
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(32)
        }
    }

    // MARK: - CSV table

    @ViewBuilder
    private func csvTable(_ rows: [[String]]) -> some View {
        if rows.isEmpty {
            centeredMessage(icon: "tablecells", text: "Empty CSV")
        } else {
            let columns = rows.map(\.count).max() ?? 0
            ScrollView([.horizontal, .vertical]) {
                Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { rowIdx, row in
                        GridRow {
                            ForEach(0..<columns, id: \.self) { colIdx in
                                Text(colIdx < row.count ? row[colIdx] : "")
                                    .font(.system(size: 11.5,
                                                  weight: rowIdx == 0 ? .semibold : .regular,
                                                  design: .monospaced))
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                    .frame(maxWidth: 280, alignment: .leading)
                                    .fixedSize(horizontal: true, vertical: false)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 5)
                            }
                        }
                        .background(rowIdx == 0
                                    ? Color.primary.opacity(0.08)
                                    : (rowIdx % 2 == 0 ? Color.primary.opacity(0.025) : Color.clear))
                    }
                    if rows.count >= Self.maxCSVRows {
                        GridRow {
                            Text("… preview truncated at \(Self.maxCSVRows) rows")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.secondary)
                                .padding(10)
                                .gridCellColumns(max(columns, 1))
                        }
                    }
                }
                .padding(12)
            }
            .background(Color.appBackground)
        }
    }

    /// Minimal RFC-4180-ish parser: handles quoted fields (embedded separators,
    /// doubled quotes, newlines inside quotes). Good enough for previews.
    static func parseCSV(_ text: String, separator: Character, maxRows: Int) -> [[String]] {
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var inQuotes = false
        var i = text.startIndex

        while i < text.endIndex, rows.count < maxRows {
            let ch = text[i]
            if inQuotes {
                if ch == "\"" {
                    let next = text.index(after: i)
                    if next < text.endIndex, text[next] == "\"" {
                        field.append("\"")
                        i = next
                    } else {
                        inQuotes = false
                    }
                } else {
                    field.append(ch)
                }
            } else {
                switch ch {
                case "\"":
                    inQuotes = true
                case separator:
                    row.append(field); field = ""
                case "\r":
                    break
                case "\n":
                    row.append(field); field = ""
                    rows.append(row); row = []
                default:
                    field.append(ch)
                }
            }
            i = text.index(after: i)
        }
        if !field.isEmpty || !row.isEmpty {
            row.append(field)
            rows.append(row)
        }
        // Drop a trailing fully-empty row from a terminating newline.
        if rows.last?.allSatisfy(\.isEmpty) == true { rows.removeLast() }
        return rows
    }

    private static func decodeText(_ data: Data) -> String? {
        String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1)
    }

    // MARK: - Shared bits

    private var loadingView: some View {
        ProgressView().tint(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func centeredMessage(icon: String, text: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 32))
                .foregroundColor(.secondary)
            Text(text).foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadRemote(_ apply: @MainActor (Data) -> Void) async {
        guard let url = URL(string: file.storageUrl) else {
            await MainActor.run { loadError = "Invalid URL" }
            return
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            await MainActor.run { apply(data) }
        } catch {
            await MainActor.run {
                loadError = "Failed to load file: \(error.localizedDescription)"
            }
        }
    }
}
