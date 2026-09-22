import SwiftUI
import UniformTypeIdentifiers
import SafariServices

struct MobileProjectFiles: View {
    let vm: ProjectDetailViewModel
    let projectId: String
    @State private var importing = false
    @State private var busy = false
    @State private var error: String?
    @State private var folderId = ""
    @State private var folderName = ""
    @State private var creatingFolder = false
    @State private var deleting: MWProjectFile?
    private var visible: [MWProjectFile] { vm.files.filter { ($0.folderId ?? "") == folderId } }

    var body: some View {
        List {
            Section {
                Picker("Folder", selection: $folderId) {
                    Text("Project files").tag("")
                    ForEach(vm.folders) { Text($0.name).tag($0.id) }
                }
                HStack {
                    Button("Upload file", systemImage: "arrow.up.doc") { importing = true }
                    Spacer()
                    if busy { ProgressView() }
                    Button("New folder", systemImage: "folder.badge.plus") { creatingFolder = true }.labelStyle(.iconOnly)
                }.disabled(busy || vm.project?.mobileCanEdit != true)
            }
            if visible.isEmpty {
                EspressoEmptyState(title: "Everything, in one place", message: "Add files, photos, and references to this project's library.", symbol: "tray")
                    .listRowBackground(Color.clear)
            }
            ForEach(visible) { file in
                MobileFileLink(file: file)
                    .swipeActions {
                        if vm.project?.mobileCanEdit == true { Button("Delete", role: .destructive) { deleting = file } }
                    }
                    .contextMenu {
                        if vm.project?.mobileCanEdit == true {
                        Menu("Move to folder") {
                            Button("Project files") { move(file, to: nil) }
                            ForEach(vm.folders) { folder in Button(folder.name) { move(file, to: folder.id) } }
                        }
                        }
                    }
            }
        }
        .scrollContentBackground(.hidden).espressoBackground()
        .refreshable { await vm.loadProject(id: projectId) }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.item]) { result in
            run {
                let file = try await MobileFileUpload.read(result.get())
                let uploaded = try await MatchaWorkService.shared.uploadProjectFile(projectId: projectId, file: file)
                vm.files.insert(uploaded, at: 0)
                // Upload is a completed operation even if a subsequent folder
                // move fails. Keep the file in root; never silently re-upload.
                let destination = folderId.isEmpty ? nil : folderId
                folderId = ""
                if let destination {
                    do {
                        let moved = try await MatchaWorkService.shared.moveProjectFile(projectId: projectId, fileId: uploaded.id, folderId: destination)
                        replace(moved); folderId = destination
                    } catch { self.error = "Uploaded to Project files, but couldn't move it: \(error.localizedDescription)" }
                }
            }
        }
        .alert("New folder", isPresented: $creatingFolder) {
            TextField("Folder name", text: $folderName)
            Button("Cancel", role: .cancel) { folderName = "" }
            Button("Create") {
                let name = folderName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !name.isEmpty else { return }
                run {
                    let folder = try await MatchaWorkService.shared.createProjectFolder(projectId: projectId, name: name)
                    vm.folders.append(folder); folderName = ""
                }
            }
        }
        .confirmationDialog("Permanently delete this file?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            if let file = deleting {
                Button("Delete \(file.filename)", role: .destructive) {
                    run {
                        try await MatchaWorkService.shared.deleteProjectFile(projectId: projectId, fileId: file.id)
                        vm.files.removeAll { $0.id == file.id }
                    }
                }
            }
        }.espressoError($error)
    }

    private func replace(_ file: MWProjectFile) {
        if let index = vm.files.firstIndex(where: { $0.id == file.id }) { vm.files[index] = file }
    }
    private func move(_ file: MWProjectFile, to folder: String?) {
        run { replace(try await MatchaWorkService.shared.moveProjectFile(projectId: projectId, fileId: file.id, folderId: folder)) }
    }
    private func run(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true; error = nil
        Task {
            defer { busy = false }
            do { try await operation() } catch { self.error = error.localizedDescription }
        }
    }
}

struct MobileFileLink: View {
    let file: MWProjectFile
    @State private var preview = false
    var body: some View {
        Group {
            if SafeURL.isAllowed(file.storageUrl), let url = URL(string: file.storageUrl) {
                Button { preview = true } label: { row }.buttonStyle(.plain)
                    .sheet(isPresented: $preview) { MobileFilePreview(url: url).ignoresSafeArea() }
            } else { row }
        }
    }
    private var row: some View {
        HStack(spacing: 14) {
            Image(systemName: file.isImage ? "photo" : "doc").font(.title2).foregroundStyle(EspressoStyle.accent)
            VStack(alignment: .leading, spacing: 4) {
                Text(file.filename).font(.subheadline.weight(.medium))
                Text(ByteCountFormatter.string(fromByteCount: Int64(file.fileSize), countStyle: .file)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "arrow.up.right").font(.caption).foregroundStyle(.secondary)
        }.padding(.vertical, 6)
    }
}

private struct MobileFilePreview: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

enum MobileFileUpload {
    /// Bound memory use before loading a security-scoped document. Blocking
    /// iCloud/document reads run off the main actor so the sheet stays responsive.
    static func read(_ url: URL) async throws -> (data: Data, filename: String, mimeType: String) {
        try await Task.detached(priority: .userInitiated) {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            let limit = 20 * 1024 * 1024
            let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .contentTypeKey])
            guard values.isRegularFile == true, let size = values.fileSize, size <= limit else {
                throw UploadError.tooLarge
            }
            let data = try Data(contentsOf: url, options: .mappedIfSafe)
            guard data.count <= limit else { throw UploadError.tooLarge }
            return (data, url.lastPathComponent, values.contentType?.preferredMIMEType ?? "application/octet-stream")
        }.value
    }
    enum UploadError: LocalizedError {
        case tooLarge
        var errorDescription: String? { "Choose a single file smaller than 20 MB. Larger uploads are available on desktop." }
    }
}
