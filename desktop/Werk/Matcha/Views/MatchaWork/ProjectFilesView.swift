import SwiftUI
import UniformTypeIdentifiers
import AppKit

// MARK: - Files View

struct ProjectFilesView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var isDragOver = false
    @State private var uploadingName: String?
    @State private var previewFile: MWProjectFile?
    @State private var isCreatingFolder = false
    @State private var newFolderName = ""
    @State private var openFolderId: String?
    @State private var fileError: String?
    @FocusState private var isFolderNameFocused: Bool

    private func files(in folderId: String) -> [MWProjectFile] {
        viewModel.files.filter { $0.folderId == folderId }
    }

    private var isEmpty: Bool {
        viewModel.folders.isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbarRow
            Divider().opacity(0.2)
            if let err = fileError {
                Text(err)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .padding(.horizontal, 12).padding(.vertical, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.red.opacity(0.08))
                Divider().opacity(0.2)
            }
            if viewModel.isLoadingFiles && isEmpty && openFolderId == nil {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if isEmpty && openFolderId == nil {
                emptyFolderState
                Spacer()
                VStack(spacing: 4) {
                    Text("Create folders to keep your files organized.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    let unfiledCount = viewModel.files.filter { $0.folderId == nil }.count
                    if unfiledCount > 0 {
                        Text("\(unfiledCount) unfiled file\(unfiledCount == 1 ? "" : "s") in Media ↑")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }
                Spacer()
            } else {
                contentList
            }
        }
        .background(Color.appBackground)
        .task {
            viewModel.errorMessage = nil
            fileError = nil
            await viewModel.ensureFilesFresh()
        }
        .onChange(of: viewModel.errorMessage) { _, msg in
            fileError = msg
        }
        .onReceive(NotificationCenter.default.publisher(for: .mwCollabFilesBrowse)) { _ in
            browse()
        }
        .sheet(item: $previewFile) { file in
            AttachmentPreviewSheet(file: file)
        }
        .onChange(of: isCreatingFolder) { _, val in
            if val { isFolderNameFocused = true }
        }
    }

    // MARK: - Toolbar

    private var toolbarRow: some View {
        HStack(spacing: 6) {
            if let fid = openFolderId,
               let folder = viewModel.folders.first(where: { $0.id == fid }) {
                Button {
                    openFolderId = nil
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left").font(.system(size: 9, weight: .semibold))
                        Text("Folders")
                    }
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
                Text("·").font(.system(size: 10)).foregroundColor(.secondary.opacity(0.5))
                Text(folder.name)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                Spacer()
                if let name = uploadingName {
                    Text("Uploading \(name)…")
                        .font(.system(size: 10))
                        .foregroundColor(.matcha500)
                } else {
                    Button("browse") { browse() }
                        .buttonStyle(.plain)
                        .font(.system(size: 10))
                        .foregroundColor(.matcha500)
                }
            } else {
                Image(systemName: "folder")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("Folders organize your files.")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Spacer()
                Button {
                    newFolderName = ""
                    isCreatingFolder = true
                } label: {
                    HStack(spacing: 3) {
                        Image(systemName: "folder.badge.plus")
                        Text("New Folder")
                    }
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Create a folder")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Content list

    private var contentList: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                if let fid = openFolderId {
                    let folderFiles = files(in: fid)
                    if folderFiles.isEmpty {
                        Text("No files — drop or browse to add.")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .padding(.top, 20)
                            .frame(maxWidth: .infinity)
                    } else {
                        ForEach(folderFiles) { file in
                            fileRow(file)
                        }
                    }
                    folderDropZone(folderId: fid)
                } else {
                    if isCreatingFolder {
                        newFolderRow
                    }
                    ForEach(viewModel.folders) { folder in
                        FolderRow(
                            folder: folder,
                            fileCount: files(in: folder.id).count,
                            onOpen: { openFolderId = folder.id },
                            onRename: { name in Task { await viewModel.renameFolder(id: folder.id, name: name) } },
                            onDelete: { Task { await viewModel.deleteFolder(id: folder.id) } },
                            onDropFileId: { fileId in
                                Task { await viewModel.moveFile(id: fileId, toFolder: folder.id) }
                            }
                        )
                    }
                }
            }
            .padding(10)
        }
    }

    @ViewBuilder
    private var newFolderRow: some View {
        HStack(spacing: 8) {
            Image(systemName: "folder.badge.plus")
                .font(.system(size: 13))
                .foregroundColor(.matcha500)
            TextField("Folder name", text: $newFolderName)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .focused($isFolderNameFocused)
                .onSubmit { commitNewFolder() }
                .onKeyPress(.escape) { cancelNewFolder(); return .handled }
            Button { commitNewFolder() } label: {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            .help("Create folder")
            Button { cancelNewFolder() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Cancel")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(Color.matcha500.opacity(0.08))
        .cornerRadius(4)
    }

    private func commitNewFolder() {
        let name = newFolderName
        isCreatingFolder = false
        newFolderName = ""
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        Task { await viewModel.createFolder(name: name) }
    }

    private func cancelNewFolder() {
        isCreatingFolder = false
        newFolderName = ""
    }

    private func fileRow(_ file: MWProjectFile) -> some View {
        FileRow(
            file: file,
            folders: viewModel.folders,
            indent: false,
            onOpen: { previewFile = file },
            onDelete: { Task { await viewModel.deleteFile(id: file.id) } },
            onMove: { target in Task { await viewModel.moveFile(id: file.id, toFolder: target) } }
        )
        .onDrag { NSItemProvider(object: file.id as NSString) }
    }

    private func folderDropZone(folderId: String) -> some View {
        VStack(spacing: 4) {
            Image(systemName: "square.and.arrow.up")
                .font(.system(size: 16))
                .foregroundColor(isDragOver ? .matcha500 : .secondary)
            if let name = uploadingName {
                Text("Uploading \(name)…")
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
            } else {
                Text("Drop or browse to add files")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(isDragOver ? Color.matcha500.opacity(0.08) : Color.zinc900.opacity(0.5))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(isDragOver ? Color.matcha500 : Color.zinc800,
                        style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        )
        .padding(.vertical, 4)
        .onDrop(of: [.fileURL], isTargeted: $isDragOver) { providers in
            handleDrop(providers, folderId: folderId)
            return true
        }
    }

    // MARK: - Empty state

    private var emptyFolderState: some View {
        VStack(spacing: 4) {
            Image(systemName: "folder")
                .font(.system(size: 18))
                .foregroundColor(.secondary)
            Text("No folders yet")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Color.zinc900.opacity(0.5))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.zinc800, style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
        )
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }

    private func handleDrop(_ providers: [NSItemProvider], folderId: String? = nil) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil),
                      let fileData = try? Data(contentsOf: url) else { return }
                let ext = url.pathExtension.lowercased()
                let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
                Task { @MainActor in uploadingName = url.lastPathComponent }
                Task {
                    if let fid = folderId {
                        await viewModel.uploadFile(data: fileData, filename: url.lastPathComponent, mimeType: mime, folderId: fid)
                    } else {
                        await viewModel.uploadFile(data: fileData, filename: url.lastPathComponent, mimeType: mime)
                    }
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
                    if let fid = openFolderId {
                        await viewModel.uploadFile(data: data, filename: url.lastPathComponent, mimeType: mime, folderId: fid)
                    } else {
                        await viewModel.uploadFile(data: data, filename: url.lastPathComponent, mimeType: mime)
                    }
                    await MainActor.run { uploadingName = nil }
                }
            }
        }
    }
}

// MARK: - Folder row

private struct FolderRow: View {
    let folder: MWProjectFolder
    let fileCount: Int
    let onOpen: () -> Void
    let onRename: (String) -> Void
    let onDelete: () -> Void
    let onDropFileId: (String) -> Void
    @State private var isHovered = false
    @State private var isTargeted = false
    @State private var isRenaming = false
    @State private var renameText = ""
    @FocusState private var isRenameFocused: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "folder.fill")
                .font(.system(size: 13))
                .foregroundColor(.matcha500)
            if isRenaming {
                TextField("Folder name", text: $renameText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12, weight: .medium))
                    .focused($isRenameFocused)
                    .onSubmit { commitRename() }
                    .onKeyPress(.escape) { cancelRename(); return .handled }
                Button { commitRename() } label: {
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
                Button { cancelRename() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            } else {
                Text(folder.name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text("\(fileCount)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.4))
                Spacer()
                if isHovered {
                    Button { startRename() } label: {
                        Image(systemName: "pencil")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Rename")
                    Button(action: onDelete) {
                        Image(systemName: "trash")
                            .font(.system(size: 10))
                            .foregroundColor(.red.opacity(0.8))
                    }
                    .buttonStyle(.plain)
                    .help("Delete folder (files move to root)")
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isTargeted ? Color.matcha500.opacity(0.18) : (isHovered ? Color.zinc800 : Color.clear))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture { if !isRenaming { onOpen() } }
        .contextMenu {
            Button("Rename") { startRename() }
            Button("Delete folder", role: .destructive, action: onDelete)
        }
        .onDrop(of: [.text], isTargeted: $isTargeted) { providers in
            guard let provider = providers.first else { return false }
            _ = provider.loadObject(ofClass: NSString.self) { obj, _ in
                if let fileId = obj as? String {
                    DispatchQueue.main.async { onDropFileId(fileId) }
                }
            }
            return true
        }
        .onChange(of: isRenaming) { _, val in
            if val { isRenameFocused = true }
        }
    }

    private func startRename() {
        renameText = folder.name
        isRenaming = true
    }

    private func commitRename() {
        let name = renameText
        isRenaming = false
        renameText = ""
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        onRename(name)
    }

    private func cancelRename() {
        isRenaming = false
        renameText = ""
    }
}

// MARK: - File row

private struct FileRow: View {
    let file: MWProjectFile
    let folders: [MWProjectFolder]
    let indent: Bool
    let onOpen: () -> Void
    let onDelete: () -> Void
    let onMove: (String?) -> Void
    @State private var isHovered = false

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        HStack(spacing: 8) {
            if indent { Spacer().frame(width: 18) }
            if file.isImage, let url = URL(string: file.storageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().interpolation(.medium).scaledToFill()
                    case .failure:
                        Color.zinc800.overlay(
                            Image(systemName: "photo").font(.system(size: 11)).foregroundColor(.secondary))
                    default:
                        Color.zinc800.overlay(ProgressView().controlSize(.small))
                    }
                }
                .frame(width: 34, height: 34)
                .clipShape(RoundedRectangle(cornerRadius: 4))
            } else {
                Image(systemName: "doc")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .frame(width: 34, height: 34)
            }
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
        .contextMenu {
            Button("Open", action: onOpen)
            if !folders.isEmpty || file.folderId != nil {
                Menu("Move to") {
                    if file.folderId != nil {
                        Button("Remove from folder") { onMove(nil) }
                        Divider()
                    }
                    ForEach(folders) { folder in
                        if folder.id != file.folderId {
                            Button(folder.name) { onMove(folder.id) }
                        }
                    }
                }
            }
            Divider()
            Button("Delete", role: .destructive, action: onDelete)
        }
    }
}

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
            if let url = URL(string: link.url) { NSWorkspace.shared.open(url) }
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

// MARK: - Elements (context repository)

/// Lists a project's elements ("what tickets are about"). Each element is a
/// context repository — tap into `ElementDetailView` to browse its folders,
/// files, notes, and the tickets scoped to it.
struct ElementsView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var selected: MWProjectElement?
    @State private var isCreating = false
    @State private var newName = ""
    @State private var showWizard = false
    @AppStorage("mw-elements-wizard-shown-v1") private var hasSeenWizard = false
    @FocusState private var nameFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            if let el = selected {
                ElementDetailView(
                    viewModel: viewModel,
                    element: el,
                    onBack: { selected = nil }
                )
            } else {
                listHeader
                Divider().opacity(0.2)
                listContent
            }
        }
        .background(Color.appBackground)
        .task {
            if viewModel.elements.isEmpty { await viewModel.loadElements() }
            if viewModel.tasks.isEmpty { Task.detached { await viewModel.loadTasks() } }
            // First-run nudge: introduce elements once, only when there's
            // nothing here yet. Re-openable later via the "?" button.
            if !hasSeenWizard && viewModel.elements.isEmpty && selected == nil {
                showWizard = true
            }
        }
        .onChange(of: isCreating) { _, v in if v { nameFocused = true } }
        .sheet(isPresented: $showWizard) {
            ElementsWizardView(
                onClose: { hasSeenWizard = true; showWizard = false },
                onCreateFirst: {
                    hasSeenWizard = true
                    showWizard = false
                    newName = ""
                    isCreating = true
                }
            )
        }
    }

    private var listHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "square.stack.3d.up")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Text("What your tickets are about — each holds its own context.")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Spacer()
            Button {
                showWizard = true
            } label: {
                Image(systemName: "questionmark.circle")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("How elements work")
            Button {
                newName = ""
                isCreating = true
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "plus")
                    Text("New Element")
                }
                .font(.system(size: 10))
                .foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private var listContent: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                if isCreating {
                    HStack(spacing: 8) {
                        Image(systemName: "square.stack.3d.up.fill")
                            .font(.system(size: 13)).foregroundColor(.matcha500)
                        TextField("Element name (e.g. Inventory)", text: $newName)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .focused($nameFocused)
                            .onSubmit { commitNew() }
                            .onKeyPress(.escape) { isCreating = false; return .handled }
                        Button { commitNew() } label: {
                            Image(systemName: "checkmark").font(.system(size: 10, weight: .semibold))
                                .foregroundColor(.matcha500)
                        }.buttonStyle(.plain)
                        Button { isCreating = false } label: {
                            Image(systemName: "xmark").font(.system(size: 10)).foregroundColor(.secondary)
                        }.buttonStyle(.plain)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 6)
                    .background(Color.matcha500.opacity(0.08)).cornerRadius(4)
                }
                if viewModel.elements.isEmpty && !isCreating {
                    Text("No elements yet. Create one (e.g. “Inventory”) to start collecting context.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 24).padding(.horizontal, 24)
                        .frame(maxWidth: .infinity)
                }
                ForEach(viewModel.elements) { el in
                    elementRow(el)
                }
            }
            .padding(10)
        }
    }

    private func elementRow(_ el: MWProjectElement) -> some View {
        let ticketCount = viewModel.tasks.filter { $0.elementId == el.id }.count
        return HStack(spacing: 8) {
            Image(systemName: "square.stack.3d.up.fill")
                .font(.system(size: 13)).foregroundColor(.matcha500)
            VStack(alignment: .leading, spacing: 1) {
                Text(el.name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white).lineLimit(1)
                if let d = el.description, !d.isEmpty {
                    Text(d).font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                }
            }
            Spacer()
            if ticketCount > 0 {
                Text("\(ticketCount) ticket\(ticketCount == 1 ? "" : "s")")
                    .font(.system(size: 9)).foregroundColor(.secondary)
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary.opacity(0.4))
        }
        .padding(.horizontal, 8).padding(.vertical, 7)
        .background(Color.zinc900.opacity(0.4)).cornerRadius(5)
        .contentShape(Rectangle())
        .onTapGesture { selected = el }
    }

    private func commitNew() {
        let n = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        isCreating = false
        newName = ""
        guard !n.isEmpty else { return }
        Task { await viewModel.createElement(name: n, kind: nil, description: nil, assignedTo: nil) }
    }
}

/// One element's context repository: folder tree + files + notes/links, plus
/// the tickets scoped to it. Self-contained state (loads element-scoped data
/// directly) so it never collides with the project's root Files/Media.
struct ElementDetailView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    let element: MWProjectElement
    let onBack: () -> Void

    @State private var files: [MWProjectFile] = []
    @State private var folders: [MWProjectFolder] = []
    @State private var notes: [MWElementNote] = []
    @State private var openFolderId: String?
    @State private var previewFile: MWProjectFile?
    @State private var uploadingName: String?
    @State private var isCreatingFolder = false
    @State private var newFolderName = ""
    @State private var newNote = ""
    @State private var newLink = ""
    @State private var loading = false
    @State private var isDragOver = false
    @FocusState private var folderFocused: Bool

    private var projectId: String? { viewModel.project?.id }
    private var tickets: [MWProjectTask] { viewModel.tasks.filter { $0.elementId == element.id } }
    private func filesIn(_ folderId: String?) -> [MWProjectFile] {
        files.filter { $0.folderId == folderId }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.2)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if let fid = openFolderId {
                        folderContents(fid)
                    } else {
                        repoSection
                        notesSection
                        ticketsSection
                    }
                }
                .padding(12)
            }
        }
        .background(Color.appBackground)
        .task { await reload() }
        .sheet(item: $previewFile) { f in AttachmentPreviewSheet(file: f) }
        .onChange(of: isCreatingFolder) { _, v in if v { folderFocused = true } }
    }

    // MARK: header

    private var header: some View {
        HStack(spacing: 6) {
            Button(action: onBack) {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left").font(.system(size: 9, weight: .semibold))
                    Text("Elements")
                }
                .font(.system(size: 10)).foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            Text("·").font(.system(size: 10)).foregroundColor(.secondary.opacity(0.5))
            Image(systemName: "square.stack.3d.up.fill")
                .font(.system(size: 11)).foregroundColor(.matcha500)
            Text(element.name)
                .font(.system(size: 12, weight: .semibold)).foregroundColor(.white).lineLimit(1)
            Spacer()
            if let name = uploadingName {
                Text("Uploading \(name)…").font(.system(size: 10)).foregroundColor(.matcha500)
            } else {
                Button("browse") { browse(folderId: openFolderId) }
                    .buttonStyle(.plain).font(.system(size: 10)).foregroundColor(.matcha500)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
    }

    // MARK: repo (folders + root files)

    @ViewBuilder
    private var repoSection: some View {
        if let d = element.description, !d.isEmpty {
            Text(d).font(.system(size: 12)).foregroundColor(.white.opacity(0.85))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        HStack(spacing: 5) {
            Image(systemName: "folder").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
            Text("FILES & FOLDERS").font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary).tracking(0.5)
            Spacer()
            Button {
                newFolderName = ""
                isCreatingFolder = true
            } label: {
                HStack(spacing: 3) { Image(systemName: "folder.badge.plus"); Text("New Folder") }
                    .font(.system(size: 10)).foregroundColor(.secondary)
            }.buttonStyle(.plain)
        }
        if isCreatingFolder {
            HStack(spacing: 8) {
                Image(systemName: "folder.badge.plus").font(.system(size: 13)).foregroundColor(.matcha500)
                TextField("Folder name (e.g. invoices)", text: $newFolderName)
                    .textFieldStyle(.plain).font(.system(size: 12))
                    .focused($folderFocused)
                    .onSubmit { commitFolder() }
                    .onKeyPress(.escape) { isCreatingFolder = false; return .handled }
                Button { commitFolder() } label: {
                    Image(systemName: "checkmark").font(.system(size: 10, weight: .semibold)).foregroundColor(.matcha500)
                }.buttonStyle(.plain)
                Button { isCreatingFolder = false } label: {
                    Image(systemName: "xmark").font(.system(size: 10)).foregroundColor(.secondary)
                }.buttonStyle(.plain)
            }
            .padding(.horizontal, 8).padding(.vertical, 6)
            .background(Color.matcha500.opacity(0.08)).cornerRadius(4)
        }
        ForEach(folders) { folder in
            FolderRow(
                folder: folder,
                fileCount: filesIn(folder.id).count,
                onOpen: { openFolderId = folder.id },
                onRename: { name in Task { await rename(folder.id, name) } },
                onDelete: { Task { await deleteFolder(folder.id) } },
                onDropFileId: { fileId in Task { await move(fileId, to: folder.id) } }
            )
        }
        // Element-root files (not in a sub-folder).
        ForEach(filesIn(nil)) { file in
            fileRow(file)
        }
        rootDropZone
    }

    private var rootDropZone: some View {
        dropZone(folderId: nil)
    }

    @ViewBuilder
    private func folderContents(_ fid: String) -> some View {
        HStack(spacing: 6) {
            Button { openFolderId = nil } label: {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left").font(.system(size: 9, weight: .semibold))
                    Text(element.name)
                }.font(.system(size: 10)).foregroundColor(.matcha500)
            }.buttonStyle(.plain)
            if let f = folders.first(where: { $0.id == fid }) {
                Text("· \(f.name)").font(.system(size: 10, weight: .medium)).foregroundColor(.secondary)
            }
            Spacer()
        }
        let folderFiles = filesIn(fid)
        if folderFiles.isEmpty {
            Text("No files — drop or browse to add.")
                .font(.system(size: 11)).foregroundColor(.secondary)
                .frame(maxWidth: .infinity).padding(.top, 12)
        } else {
            ForEach(folderFiles) { fileRow($0) }
        }
        dropZone(folderId: fid)
    }

    private func fileRow(_ file: MWProjectFile) -> some View {
        FileRow(
            file: file,
            folders: folders,
            indent: false,
            onOpen: { previewFile = file },
            onDelete: { Task { await deleteFile(file.id) } },
            onMove: { target in Task { await move(file.id, to: target) } }
        )
        .onDrag { NSItemProvider(object: file.id as NSString) }
    }

    private func dropZone(folderId: String?) -> some View {
        VStack(spacing: 4) {
            Image(systemName: "square.and.arrow.up")
                .font(.system(size: 15)).foregroundColor(isDragOver ? .matcha500 : .secondary)
            Text(uploadingName.map { "Uploading \($0)…" } ?? "Drop or browse to add files")
                .font(.system(size: 10)).foregroundColor(uploadingName != nil ? .matcha500 : .secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 12)
        .background(isDragOver ? Color.matcha500.opacity(0.08) : Color.zinc900.opacity(0.5))
        .overlay(RoundedRectangle(cornerRadius: 6)
            .stroke(isDragOver ? Color.matcha500 : Color.zinc800, style: StrokeStyle(lineWidth: 1, dash: [4, 4])))
        .onDrop(of: [.fileURL], isTargeted: $isDragOver) { providers in
            handleDrop(providers, folderId: folderId); return true
        }
    }

    // MARK: notes / links

    @ViewBuilder
    private var notesSection: some View {
        HStack(spacing: 5) {
            Image(systemName: "text.bubble").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
            Text("NOTES & LINKS").font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary).tracking(0.5)
        }
        ForEach(notes) { note in noteRow(note) }
        HStack(spacing: 6) {
            TextField("Add a note…", text: $newNote)
                .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white)
                .padding(7).background(Color.zinc800.opacity(0.6)).cornerRadius(5)
                .onSubmit { Task { await addNote() } }
            Button { Task { await addNote() } } label: {
                Text("Add").font(.system(size: 12, weight: .semibold)).foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            .disabled(newNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        HStack(spacing: 6) {
            TextField("Add a link (https://…)", text: $newLink)
                .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white)
                .padding(7).background(Color.zinc800.opacity(0.6)).cornerRadius(5)
                .onSubmit { Task { await addLink() } }
            Button { Task { await addLink() } } label: {
                Image(systemName: "link.badge.plus").font(.system(size: 12)).foregroundColor(.matcha500)
            }
            .buttonStyle(.plain)
            .disabled(newLink.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    private func noteRow(_ note: MWElementNote) -> some View {
        let isLink = note.kind == "link"
        return HStack(alignment: .top, spacing: 8) {
            Image(systemName: isLink ? "link" : "text.alignleft")
                .font(.system(size: 11)).foregroundColor(.secondary).frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                if isLink, let u = note.url {
                    Text(note.body?.isEmpty == false ? note.body! : u)
                        .font(.system(size: 12)).foregroundColor(.matcha500).lineLimit(2)
                        .onTapGesture { if let url = URL(string: u) { NSWorkspace.shared.open(url) } }
                } else if let b = note.body {
                    Text(b).font(.system(size: 12)).foregroundColor(.white.opacity(0.9)).textSelection(.enabled)
                }
                Text("\(note.authorName ?? "Someone") · \(PacificDateFormatter.absolute(note.createdAt ?? "") ?? "")")
                    .font(.system(size: 9)).foregroundColor(.secondary)
            }
            Spacer()
            Button { Task { await deleteNote(note.id) } } label: {
                Image(systemName: "trash").font(.system(size: 10)).foregroundColor(.red.opacity(0.7))
            }.buttonStyle(.plain)
        }
        .padding(8).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.zinc800.opacity(0.5)).cornerRadius(5)
    }

    // MARK: tickets about this

    @ViewBuilder
    private var ticketsSection: some View {
        HStack(spacing: 5) {
            Image(systemName: "checklist").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
            Text("TICKETS ABOUT THIS").font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary).tracking(0.5)
            if !tickets.isEmpty {
                Text("\(tickets.count)").font(.system(size: 9)).foregroundColor(.secondary)
            }
        }
        if tickets.isEmpty {
            Text("No tickets scoped to this element yet. Pick it when creating a ticket.")
                .font(.system(size: 11)).foregroundColor(.secondary)
        } else {
            ForEach(tickets) { t in
                HStack(spacing: 8) {
                    Image(systemName: "circle").font(.system(size: 8)).foregroundColor(.secondary)
                    Text(t.title).font(.system(size: 12)).foregroundColor(.white).lineLimit(1)
                    Spacer()
                    Text(t.boardColumn.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 9, weight: .semibold)).foregroundColor(.matcha500)
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Color.matcha500.opacity(0.15)).cornerRadius(3)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(Color.zinc900.opacity(0.4)).cornerRadius(4)
            }
        }
    }

    // MARK: data ops

    private func reload() async {
        guard let pid = projectId else { return }
        loading = true
        async let f = MatchaWorkService.shared.listElementFiles(projectId: pid, elementId: element.id)
        async let d = MatchaWorkService.shared.listElementFolders(projectId: pid, elementId: element.id)
        async let n = MatchaWorkService.shared.listElementNotes(projectId: pid, elementId: element.id)
        files = (try? await f) ?? files
        folders = (try? await d) ?? folders
        notes = (try? await n) ?? notes
        loading = false
    }

    private func commitFolder() {
        let name = newFolderName.trimmingCharacters(in: .whitespacesAndNewlines)
        isCreatingFolder = false
        newFolderName = ""
        guard !name.isEmpty, let pid = projectId else { return }
        Task {
            if let folder = try? await MatchaWorkService.shared.createElementFolder(
                projectId: pid, elementId: element.id, name: name, parentId: nil
            ) {
                folders.append(folder)
            }
        }
    }

    private func addNote() async {
        let text = newNote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let pid = projectId else { return }
        newNote = ""
        if let n = try? await MatchaWorkService.shared.addElementNote(
            projectId: pid, elementId: element.id, kind: "note", body: text, url: nil
        ) { notes.insert(n, at: 0) }
    }

    private func addLink() async {
        let url = newLink.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty, let pid = projectId else { return }
        newLink = ""
        if let n = try? await MatchaWorkService.shared.addElementNote(
            projectId: pid, elementId: element.id, kind: "link", body: nil, url: url
        ) { notes.insert(n, at: 0) }
    }

    private func deleteNote(_ id: String) async {
        guard let pid = projectId else { return }
        notes.removeAll { $0.id == id }
        try? await MatchaWorkService.shared.deleteElementNote(projectId: pid, elementId: element.id, noteId: id)
    }

    private func deleteFile(_ id: String) async {
        guard let pid = projectId else { return }
        files.removeAll { $0.id == id }
        try? await MatchaWorkService.shared.deleteProjectFile(projectId: pid, fileId: id)
    }

    private func move(_ fileId: String, to folderId: String?) async {
        guard let pid = projectId else { return }
        if let updated = try? await MatchaWorkService.shared.moveProjectFile(projectId: pid, fileId: fileId, folderId: folderId),
           let i = files.firstIndex(where: { $0.id == fileId }) {
            files[i] = updated
        }
    }

    private func rename(_ folderId: String, _ name: String) async {
        guard let pid = projectId else { return }
        if let updated = try? await MatchaWorkService.shared.renameProjectFolder(projectId: pid, folderId: folderId, name: name),
           let i = folders.firstIndex(where: { $0.id == folderId }) {
            folders[i] = updated
        }
    }

    private func deleteFolder(_ folderId: String) async {
        guard let pid = projectId else { return }
        folders.removeAll { $0.id == folderId }
        try? await MatchaWorkService.shared.deleteProjectFolder(projectId: pid, folderId: folderId)
        await reload()
    }

    private func handleDrop(_ providers: [NSItemProvider], folderId: String?) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil),
                      let fileData = try? Data(contentsOf: url) else { return }
                let ext = url.pathExtension.lowercased()
                let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
                Task { @MainActor in uploadingName = url.lastPathComponent }
                Task { await upload(fileData, url.lastPathComponent, mime, folderId: folderId) }
            }
        }
    }

    private func browse(folderId: String?) {
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
                Task { await upload(data, url.lastPathComponent, mime, folderId: folderId) }
            }
        }
    }

    private func upload(_ data: Data, _ filename: String, _ mime: String, folderId: String?) async {
        guard let pid = projectId else { return }
        if let rec = try? await MatchaWorkService.shared.uploadElementFile(
            projectId: pid, elementId: element.id, folderId: folderId,
            file: (data: data, filename: filename, mimeType: mime)
        ) {
            files.insert(rec, at: 0)
        }
        await MainActor.run { uploadingName = nil }
    }
}

// MARK: - Elements intro wizard

/// Skippable 4-step intro shown the first time a project's Elements tab is
/// opened (when empty). Re-openable via the "?" in the Elements header.
/// Persisted dismissal lives in `@AppStorage("mw-elements-wizard-shown-v1")`
/// on the caller; this view just reports Skip / Create-first via callbacks.
struct ElementsWizardView: View {
    let onClose: () -> Void
    let onCreateFirst: () -> Void

    @State private var step = 1
    private let total = 4

    private struct Page {
        let icon: String
        let title: String
        let body: String
    }

    private var pages: [Page] {
        [
            Page(icon: "square.stack.3d.up.fill",
                 title: "Elements = what your work is about",
                 body: "Make an element for each thing your project revolves around — Inventory, Marketing, Storefront. Pick one when you create a ticket to say what it's about, so you scope work in a tap instead of writing an essay."),
            Page(icon: "folder.fill",
                 title: "Each element is its own little repo",
                 body: "Open an element to add folders (Inventory → invoices, returns) and drag in files. The inventory data lives in Inventory — it stays out of the project's general Files tab so nothing gets buried."),
            Page(icon: "text.bubble.fill",
                 title: "Pin notes & links for context",
                 body: "Drop quick notes and links onto an element. New teammates open it to learn everything tied to that thing — no more hunting through chat history to get up to speed."),
            Page(icon: "sparkles",
                 title: "Build context once, reuse it everywhere",
                 body: "Every ticket you scope to an element shows up under it, so the work and its context live together. (Soon, the AI will read element context to answer questions about your kanban and pipeline.)"),
        ]
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                ForEach(1...total, id: \.self) { i in
                    Circle()
                        .fill(i <= step ? Color.matcha500 : Color.white.opacity(0.15))
                        .frame(width: 6, height: 6)
                }
                Spacer()
                Button("Skip", action: onClose)
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 18).padding(.vertical, 12)
            Divider().opacity(0.2)

            let page = pages[step - 1]
            VStack(spacing: 14) {
                Spacer()
                Image(systemName: page.icon)
                    .font(.system(size: 40))
                    .foregroundColor(.matcha500)
                Text(page.title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                Text(page.body)
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.7))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
            }
            .padding(.horizontal, 28)
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider().opacity(0.2)
            HStack {
                if step > 1 {
                    Button("Back") { step -= 1 }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                Spacer()
                if step < total {
                    Button {
                        step += 1
                    } label: {
                        Text("Next")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 16).padding(.vertical, 7)
                            .background(Color.matcha600)
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                } else {
                    Button(action: onCreateFirst) {
                        Text("Create an element")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 16).padding(.vertical, 7)
                            .background(Color.matcha600)
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 18).padding(.vertical, 12)
        }
        .frame(width: 460, height: 420)
        .background(Color.appBackground)
    }
}
