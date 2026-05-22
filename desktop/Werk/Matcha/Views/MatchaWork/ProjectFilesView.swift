import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct ProjectFilesView: View {
    @Bindable var viewModel: ProjectDetailViewModel
    @State private var isDragOver = false
    @State private var uploadingName: String?
    @State private var previewFile: MWProjectFile?
    @State private var expandedFolders: Set<String> = []
    @State private var showNewFolder = false
    @State private var newFolderName = ""
    @State private var renamingFolder: MWProjectFolder?
    @State private var renameText = ""

    private var rootFiles: [MWProjectFile] {
        viewModel.files.filter { $0.folderId == nil }
    }

    private func files(in folderId: String) -> [MWProjectFile] {
        viewModel.files.filter { $0.folderId == folderId }
    }

    private var isEmpty: Bool {
        viewModel.files.isEmpty && viewModel.folders.isEmpty
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbarRow
            Divider().opacity(0.2)
            if viewModel.isLoadingFiles && isEmpty {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if isEmpty {
                dropZone
                Spacer()
                Text("No files yet — drop files above, or make a folder.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
            } else {
                contentList
                    .onDrop(of: [.fileURL], isTargeted: $isDragOver) { providers in
                        handleDrop(providers)
                        return true
                    }
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
        .alert("New folder", isPresented: $showNewFolder) {
            TextField("Folder name", text: $newFolderName)
            Button("Create") {
                let name = newFolderName
                newFolderName = ""
                Task { await viewModel.createFolder(name: name) }
            }
            Button("Cancel", role: .cancel) { newFolderName = "" }
        }
        .alert("Rename folder", isPresented: Binding(
            get: { renamingFolder != nil },
            set: { if !$0 { renamingFolder = nil } }
        )) {
            TextField("Folder name", text: $renameText)
            Button("Rename") {
                if let folder = renamingFolder {
                    let name = renameText
                    Task { await viewModel.renameFolder(id: folder.id, name: name) }
                }
                renamingFolder = nil
            }
            Button("Cancel", role: .cancel) { renamingFolder = nil }
        }
    }

    // MARK: - Toolbar

    private var toolbarRow: some View {
        HStack(spacing: 6) {
            Image(systemName: "square.and.arrow.up")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            if let name = uploadingName {
                Text("Uploading \(name)…")
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
            } else {
                Text("Drop files anywhere or")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Button("browse") { browse() }
                    .buttonStyle(.plain)
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
            }
            Spacer()
            Button {
                newFolderName = ""
                showNewFolder = true
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
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Content list

    private var contentList: some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                ForEach(viewModel.folders) { folder in
                    FolderRow(
                        folder: folder,
                        fileCount: files(in: folder.id).count,
                        isExpanded: expandedFolders.contains(folder.id),
                        onToggle: { toggle(folder.id) },
                        onRename: {
                            renameText = folder.name
                            renamingFolder = folder
                        },
                        onDelete: { Task { await viewModel.deleteFolder(id: folder.id) } },
                        onDropFileId: { fileId in
                            Task { await viewModel.moveFile(id: fileId, toFolder: folder.id) }
                        }
                    )
                    if expandedFolders.contains(folder.id) {
                        ForEach(files(in: folder.id)) { file in
                            fileRow(file, indent: true)
                        }
                    }
                }
                ForEach(rootFiles) { file in
                    fileRow(file, indent: false)
                }
            }
            .padding(10)
        }
    }

    private func fileRow(_ file: MWProjectFile, indent: Bool) -> some View {
        FileRow(
            file: file,
            folders: viewModel.folders,
            indent: indent,
            onOpen: { openFile(file) },
            onDelete: { Task { await viewModel.deleteFile(id: file.id) } },
            onMove: { target in Task { await viewModel.moveFile(id: file.id, toFolder: target) } }
        )
        .onDrag { NSItemProvider(object: file.id as NSString) }
    }

    private func toggle(_ folderId: String) {
        if expandedFolders.contains(folderId) {
            expandedFolders.remove(folderId)
        } else {
            expandedFolders.insert(folderId)
        }
    }

    // MARK: - Drop zone (empty state)

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
        previewFile = file
    }
}

// MARK: - Folder row

private struct FolderRow: View {
    let folder: MWProjectFolder
    let fileCount: Int
    let isExpanded: Bool
    let onToggle: () -> Void
    let onRename: () -> Void
    let onDelete: () -> Void
    let onDropFileId: (String) -> Void
    @State private var isHovered = false
    @State private var isTargeted = false

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary)
                .frame(width: 10)
            Image(systemName: "folder.fill")
                .font(.system(size: 13))
                .foregroundColor(.matcha500)
            Text(folder.name)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white)
                .lineLimit(1)
            Text("\(fileCount)")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Spacer()
            if isHovered {
                Button(action: onRename) {
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
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isTargeted ? Color.matcha500.opacity(0.18) : (isHovered ? Color.zinc800 : Color.clear))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture(perform: onToggle)
        .contextMenu {
            Button("Rename", action: onRename)
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
                        Button("Root (no folder)") { onMove(nil) }
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
