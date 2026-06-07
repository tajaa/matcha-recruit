import SwiftUI

// MARK: - Media View

struct ProjectMediaView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var previewFile: MWProjectFile?
    @State private var isCreatingFolder = false
    @State private var newFolderName = ""
    // When set, the new folder being created should immediately receive a copy
    // of this file ("Add to Files → New folder…").
    @State private var pendingAddToFilesFile: MWProjectFile?

    private static let bucketOrder = ["Images", "Screenshots", "Videos", "PDFs",
                                      "Audio", "Documents", "Links", "Other"]

    private var unfiledFiles: [MWProjectFile] {
        viewModel.files.filter { $0.folderId == nil }
    }

    /// Heuristic: pasted screenshots upload as `pasted-{ts}.png`; macOS / common
    /// capture tools name saved shots "Screenshot …", "Screen Shot …", "CleanShot …".
    private func isScreenshot(_ file: MWProjectFile) -> Bool {
        guard file.isImage else { return false }
        let n = file.filename.lowercased()
        return n.hasPrefix("pasted-")
            || n.contains("screenshot")
            || n.contains("screen shot")
            || n.contains("cleanshot")
    }

    private func mediaBucket(for file: MWProjectFile) -> String {
        let ct = file.contentType?.lowercased() ?? ""
        let ext = (file.filename as NSString).pathExtension.lowercased()
        if ct == "application/pdf" || ext == "pdf" { return "PDFs" }
        if isScreenshot(file) { return "Screenshots" }
        if file.isImage { return "Images" }
        let videoExts = ["mp4", "mov", "avi", "mkv", "webm", "m4v", "wmv", "flv"]
        let audioExts = ["mp3", "wav", "aac", "m4a", "flac", "ogg", "opus", "wma"]
        if ct.hasPrefix("video/") || videoExts.contains(ext) { return "Videos" }
        if ct.hasPrefix("audio/") || audioExts.contains(ext) { return "Audio" }
        let docExts = ["doc", "docx", "txt", "csv", "xls", "xlsx",
                       "ppt", "pptx", "pages", "numbers", "keynote"]
        if docExts.contains(ext) { return "Documents" }
        return "Other"
    }

    private var grouped: [(bucket: String, files: [MWProjectFile])] {
        var dict: [String: [MWProjectFile]] = [:]
        for file in unfiledFiles {
            let b = mediaBucket(for: file)
            dict[b, default: []].append(file)
        }
        return Self.bucketOrder.compactMap { b in
            guard let files = dict[b], !files.isEmpty else { return nil }
            return (bucket: b, files: files)
        }
    }

    private func bucketIcon(_ bucket: String) -> String {
        switch bucket {
        case "Images": return "photo"
        case "Screenshots": return "camera.viewfinder"
        case "Videos": return "video"
        case "PDFs": return "doc.richtext"
        case "Audio": return "music.note"
        case "Documents": return "doc.text"
        case "Links": return "link"
        default: return "doc"
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "photo.stack")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("Files dropped in chat appear here.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            Divider().opacity(0.2)
            if viewModel.isLoadingFiles && unfiledFiles.isEmpty && viewModel.links.isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if unfiledFiles.isEmpty && viewModel.links.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "photo.stack")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary.opacity(0.5))
                    Text("Nothing in media yet")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                    Text("Drop files or links in the project chat to see them here.")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary.opacity(0.7))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(grouped, id: \.bucket) { group in
                            bucketSection(group.bucket, files: group.files)
                        }
                        if !viewModel.links.isEmpty {
                            linksSection(viewModel.links)
                        }
                    }
                    .padding(10)
                }
            }
        }
        .background(Color.appBackground)
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
        .sheet(isPresented: $isCreatingFolder) {
            newFolderSheet
        }
        .task {
            // SWR: paint from cache/state, then revalidate only if stale.
            // Throttles the files + chat-sync + links refetch so re-opening
            // Media within 30s isn't 3 fresh network calls every entry.
            await viewModel.ensureMediaFresh()
        }
    }

    private var newFolderSheet: some View {
        VStack(spacing: 16) {
            Text("New Folder")
                .font(.system(size: 14, weight: .semibold))
            TextField("Folder name", text: $newFolderName)
                .textFieldStyle(.roundedBorder)
                .frame(width: 220)
                .onSubmit { commitNewFolder() }
            HStack(spacing: 8) {
                Button("Cancel") { cancelNewFolder() }
                    .keyboardShortcut(.cancelAction)
                Button("Create") { commitNewFolder() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(newFolderName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 280)
    }

    private func commitNewFolder() {
        let name = newFolderName
        let fileToAdd = pendingAddToFilesFile
        isCreatingFolder = false
        newFolderName = ""
        pendingAddToFilesFile = nil
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        Task {
            let folder = await viewModel.createFolder(name: name)
            // If this came from "Add to Files → New folder…", copy the file in.
            if let folder, let fileToAdd {
                await viewModel.copyFileToFolder(id: fileToAdd.id, toFolder: folder.id)
            }
        }
    }

    private func cancelNewFolder() {
        isCreatingFolder = false
        newFolderName = ""
        pendingAddToFilesFile = nil
    }

    private func bucketSection(_ bucket: String, files: [MWProjectFile]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: bucketIcon(bucket))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                Text(bucket)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                Text("\(files.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .padding(.horizontal, 4)

            if bucket == "Images" || bucket == "Screenshots" {
                imageGrid(files: files)
            } else {
                ForEach(files) { file in
                    mediaFileRow(file)
                }
            }
        }
    }

    private func imageGrid(files: [MWProjectFile]) -> some View {
        let cols = [GridItem(.adaptive(minimum: 72, maximum: 88), spacing: 6)]
        return LazyVGrid(columns: cols, spacing: 6) {
            ForEach(files) { file in
                AsyncImage(url: URL(string: file.storageUrl)) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFill()
                    case .failure:
                        Color.zinc800
                            .overlay(Image(systemName: "photo").foregroundColor(.secondary))
                    default:
                        Color.zinc800.overlay(ProgressView().controlSize(.small))
                    }
                }
                .frame(width: 72, height: 72)
                .clipped()
                .cornerRadius(5)
                .contentShape(Rectangle())
                .onTapGesture { previewFile = file }
                .contextMenu { mediaContextMenu(file) }
            }
        }
    }

    private func linksSection(_ links: [MWProjectLink]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: bucketIcon("Links"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                Text("Links")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)
                Text("\(links.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .padding(.horizontal, 4)

            ForEach(links) { link in
                linkRow(link)
            }
        }
    }

    private func linkRow(_ link: MWProjectLink) -> some View {
        let host = URL(string: link.url)?.host ?? link.url
        return HStack(spacing: 8) {
            Image(systemName: "link")
                .font(.system(size: 13))
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(host)
                        .font(.system(size: 12))
                        .foregroundColor(.white)
                        .lineLimit(1)
                    if let sender = link.senderName, !sender.isEmpty {
                        Text("· \(sender)")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary.opacity(0.7))
                            .lineLimit(1)
                    }
                }
                Text(link.url)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            Image(systemName: "arrow.up.right.square")
                .font(.system(size: 11))
                .foregroundColor(.secondary.opacity(0.6))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.zinc900.opacity(0.4))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onTapGesture {
            SafeURL.open(link.url)
        }
    }

    private func mediaFileRow(_ file: MWProjectFile) -> some View {
        let bytes = Double(file.fileSize)
        let sizeLabel = bytes < 1024 ? "\(file.fileSize) B"
            : bytes < 1024 * 1024 ? String(format: "%.1f KB", bytes / 1024)
            : String(format: "%.1f MB", bytes / 1024 / 1024)

        return HStack(spacing: 8) {
            Image(systemName: bucketIcon(mediaBucket(for: file)))
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
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.zinc900.opacity(0.4))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onTapGesture { previewFile = file }
        .contextMenu { mediaContextMenu(file) }
    }

    @ViewBuilder
    private func mediaContextMenu(_ file: MWProjectFile) -> some View {
        Button("Open") { previewFile = file }
        // "Add to Files" copies the item into a folder (original stays in Media).
        Menu("Add to Files") {
            ForEach(viewModel.folders) { folder in
                Button(folder.name) {
                    Task { await viewModel.copyFileToFolder(id: file.id, toFolder: folder.id) }
                }
            }
            if !viewModel.folders.isEmpty { Divider() }
            Button("New folder…") {
                pendingAddToFilesFile = file
                newFolderName = ""
                isCreatingFolder = true
            }
        }
        Divider()
        Button("Delete", role: .destructive) {
            Task { await viewModel.deleteFile(id: file.id) }
        }
    }
}
