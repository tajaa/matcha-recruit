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
            if let err = viewModel.errorMessage {
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
                Text("Create folders to keep your files organized.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            } else {
                contentList
            }
        }
        .background(Color.appBackground)
        .task {
            if viewModel.files.isEmpty {
                await viewModel.loadFiles()
            } else {
                Task.detached { await viewModel.loadFiles() }
            }
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
            Image(systemName: file.isImage ? "photo" : "doc")
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

    private static let bucketOrder = ["Images", "Videos", "Audio", "Documents", "Other"]

    private var unfiledFiles: [MWProjectFile] {
        viewModel.files.filter { $0.folderId == nil }
    }

    private func mediaBucket(for file: MWProjectFile) -> String {
        let ct = file.contentType?.lowercased() ?? ""
        if file.isImage { return "Images" }
        if ct.hasPrefix("video/") { return "Videos" }
        if ct.hasPrefix("audio/") { return "Audio" }
        let docExts = ["pdf", "doc", "docx", "txt", "csv", "xls", "xlsx",
                       "ppt", "pptx", "pages", "numbers", "keynote"]
        let ext = (file.filename as NSString).pathExtension.lowercased()
        if ct == "application/pdf" || docExts.contains(ext) { return "Documents" }
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
        case "Videos": return "video"
        case "Audio": return "music.note"
        case "Documents": return "doc.text"
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
            if viewModel.isLoadingFiles && unfiledFiles.isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if unfiledFiles.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "photo.stack")
                        .font(.system(size: 24))
                        .foregroundColor(.secondary.opacity(0.5))
                    Text("Nothing in media yet")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                    Text("Drop files in the project chat to see them here.")
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
            if viewModel.files.isEmpty {
                await viewModel.loadFiles()
            }
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
        isCreatingFolder = false
        newFolderName = ""
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        Task { await viewModel.createFolder(name: name) }
    }

    private func cancelNewFolder() {
        isCreatingFolder = false
        newFolderName = ""
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

            if bucket == "Images" {
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
        if !viewModel.folders.isEmpty {
            Menu("Move to folder") {
                ForEach(viewModel.folders) { folder in
                    Button(folder.name) {
                        Task { await viewModel.moveFile(id: file.id, toFolder: folder.id) }
                    }
                }
            }
        }
        Button("New folder…") {
            newFolderName = ""
            isCreatingFolder = true
        }
        Divider()
        Button("Delete", role: .destructive) {
            Task { await viewModel.deleteFile(id: file.id) }
        }
    }
}
