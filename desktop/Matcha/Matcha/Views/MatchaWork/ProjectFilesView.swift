import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ProjectFilesView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var isDragOver = false
    @State private var uploadingName: String?

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider().opacity(0.3)
            dropZone
            Divider().opacity(0.3)
            if viewModel.isLoadingFiles && viewModel.files.isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if viewModel.files.isEmpty {
                Spacer()
                Text("No files yet — drop files above or click Browse.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            } else {
                fileList
            }
        }
        .background(Color.appBackground)
        .task { await viewModel.loadFiles() }
    }

    private var headerBar: some View {
        HStack {
            Text("Files")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button { browse() } label: {
                Text("Browse")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            Button { Task { await viewModel.loadFiles() } } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var dropZone: some View {
        VStack(spacing: 4) {
            Image(systemName: "square.and.arrow.up")
                .font(.system(size: 18))
                .foregroundColor(isDragOver ? .matcha500 : .secondary)
            if let name = uploadingName {
                Text("Uploading \(name)…")
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
            } else {
                Text("Drop files here")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(isDragOver ? Color.matcha500.opacity(0.08) : Color.zinc900.opacity(0.5))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isDragOver ? Color.matcha500 : Color.zinc800, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        )
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .onDrop(of: [.fileURL], isTargeted: $isDragOver) { providers in
            handleDrop(providers)
            return true
        }
    }

    private var fileList: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                ForEach(viewModel.files) { file in
                    FileRow(file: file) {
                        openFile(file)
                    } onDelete: {
                        Task { await viewModel.deleteFile(id: file.id) }
                    }
                }
            }
            .padding(10)
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil),
                      let fileData = try? Data(contentsOf: url) else { return }
                let ext = url.pathExtension.lowercased()
                let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
                Task { @MainActor in uploadingName = url.lastPathComponent }
                Task {
                    await viewModel.uploadFile(
                        data: fileData, filename: url.lastPathComponent, mimeType: mime
                    )
                    await MainActor.run { uploadingName = nil }
                }
            }
        }
    }

    private func browse() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.begin { response in
            guard response == .OK else { return }
            for url in panel.urls {
                guard let data = try? Data(contentsOf: url) else { continue }
                let ext = url.pathExtension.lowercased()
                let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
                Task { @MainActor in uploadingName = url.lastPathComponent }
                Task {
                    await viewModel.uploadFile(
                        data: data, filename: url.lastPathComponent, mimeType: mime
                    )
                    await MainActor.run { uploadingName = nil }
                }
            }
        }
    }

    private func openFile(_ file: MWProjectFile) {
        guard let url = URL(string: file.storageUrl) else { return }
        NSWorkspace.shared.open(url)
    }
}

private struct FileRow: View {
    let file: MWProjectFile
    let onOpen: () -> Void
    let onDelete: () -> Void
    @State private var isHovered = false

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "doc")
                .font(.system(size: 13))
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(file.filename)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text(sizeLabel)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            if isHovered {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Delete")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isHovered ? Color.zinc800 : Color.clear)
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture(perform: onOpen)
    }
}
