import SwiftUI
import UniformTypeIdentifiers
import AppKit

/// Sheet to connect / change a project's GitHub repo (owner/name + optional
/// branch). Validation happens server-side on connect (the read-only token must
/// be able to read it).
struct GitHubConnectSheet: View {
    let currentRepo: String?
    let currentBranch: String?
    let onConnect: (_ repo: String, _ branch: String?) async -> Void
    let onClose: () -> Void

    @State private var repo: String
    @State private var branch: String
    @State private var connecting = false

    init(currentRepo: String?, currentBranch: String?,
         onConnect: @escaping (_ repo: String, _ branch: String?) async -> Void,
         onClose: @escaping () -> Void) {
        self.currentRepo = currentRepo
        self.currentBranch = currentBranch
        self.onConnect = onConnect
        self.onClose = onClose
        _repo = State(initialValue: currentRepo ?? "")
        _branch = State(initialValue: currentBranch ?? "")
    }

    private var trimmedRepo: String { repo.trimmingCharacters(in: .whitespaces) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Connect GitHub repo").font(.system(size: 15, weight: .semibold)).foregroundColor(.white)
            Text("The server reads this repo with its read-only token — for commit→subtask check-off and Prop code chat. No local clone.")
                .font(.system(size: 11)).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 4) {
                Text("REPOSITORY").font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary).tracking(0.5)
                TextField("owner/name (e.g. tajaa/matcha-recruit)", text: $repo)
                    .textFieldStyle(.plain).font(.system(size: 12, design: .monospaced)).foregroundColor(.white)
                    .padding(8).background(Color.zinc800.opacity(0.6)).cornerRadius(6)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("BRANCH (optional)").font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary).tracking(0.5)
                TextField("default branch if blank (e.g. main)", text: $branch)
                    .textFieldStyle(.plain).font(.system(size: 12, design: .monospaced)).foregroundColor(.white)
                    .padding(8).background(Color.zinc800.opacity(0.6)).cornerRadius(6)
            }
            HStack {
                Spacer()
                Button("Cancel") { onClose() }.buttonStyle(.plain).foregroundColor(.secondary)
                Button {
                    connecting = true
                    let b = branch.trimmingCharacters(in: .whitespaces)
                    Task {
                        await onConnect(trimmedRepo, b.isEmpty ? nil : b)
                        connecting = false
                        onClose()
                    }
                } label: {
                    if connecting { ProgressView().controlSize(.small) }
                    else { Text("Connect").font(.system(size: 12, weight: .semibold)).foregroundColor(.white) }
                }
                .buttonStyle(.plain).padding(.horizontal, 12).padding(.vertical, 5)
                .background(Color.matcha500).cornerRadius(5)
                .disabled(connecting || trimmedRepo.isEmpty)
            }
        }
        .padding(18).frame(width: 420)
        .background(Color.appBackground)
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
    @State private var showConnectSheet = false
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
                githubBar
                Divider().opacity(0.2)
                listContent
            }
        }
        .background(Color.appBackground)
        .sheet(isPresented: $showConnectSheet) {
            GitHubConnectSheet(
                currentRepo: viewModel.connectedGitHubRepo,
                currentBranch: viewModel.connectedGitHubBranch,
                onConnect: { repo, branch in
                    await viewModel.connectGitHubRepo(repo: repo, branch: branch)
                },
                onClose: { showConnectSheet = false }
            )
        }
        .task {
            if viewModel.elements.isEmpty { await viewModel.loadElements() }
            if viewModel.tasks.isEmpty { Task.detached { await viewModel.loadTasks() } }
            await viewModel.loadCommitSuggestions()
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

    /// GitHub connection bar — connect/change the repo, then Scan commits
    /// (subtask check-off) + Sync code (Prop grounding). All server-side via the
    /// read-only token; no local clone.
    private var githubBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .font(.system(size: 10, weight: .semibold)).foregroundColor(.matcha500)
            if let repo = viewModel.connectedGitHubRepo, !repo.isEmpty {
                Text(repo).font(.system(size: 10, weight: .medium)).foregroundColor(.white).lineLimit(1)
                if let b = viewModel.connectedGitHubBranch, !b.isEmpty {
                    Text("@\(b)").font(.system(size: 9)).foregroundColor(.secondary)
                }
                if let s = viewModel.lastScanSummary ?? viewModel.lastSyncSummary {
                    Text("· \(s)").font(.system(size: 9)).foregroundColor(.secondary).lineLimit(1)
                }
            } else {
                Text("No GitHub repo connected").font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer(minLength: 6)
            if viewModel.isGitHubConnected {
                Button { Task { await viewModel.scanCommitsFromGitHub() } } label: {
                    HStack(spacing: 3) {
                        if viewModel.isScanningCommits { ProgressView().controlSize(.small) }
                        else { Image(systemName: "arrow.triangle.2.circlepath") }
                        Text("Scan commits")
                    }
                    .font(.system(size: 10)).foregroundColor(.matcha500)
                }
                .buttonStyle(.plain).disabled(viewModel.isScanningCommits)
                .help("Scan the connected branch's recent commits → check off subtasks (auto-runs when you open the Kanban)")
                Button { Task { await viewModel.syncFromGitHub() } } label: {
                    HStack(spacing: 3) {
                        if viewModel.isSyncingRepo { ProgressView().controlSize(.small) }
                        else { Image(systemName: "arrow.down.circle") }
                        Text("Sync code")
                    }
                    .font(.system(size: 10)).foregroundColor(.matcha500)
                }
                .buttonStyle(.plain).disabled(viewModel.isSyncingRepo)
                .help("Pull each bound element's code from GitHub (for Prop chats)")
                Menu {
                    Button("Enable push auto-scan") { Task { await viewModel.installGitHubWebhook() } }
                    Button("Change repo…") { showConnectSheet = true }
                    Button("Disconnect", role: .destructive) { Task { await viewModel.disconnectGitHubRepo() } }
                } label: {
                    Image(systemName: "ellipsis").font(.system(size: 11)).foregroundColor(.secondary)
                }
                .menuStyle(.borderlessButton).frame(width: 16)
            } else {
                Button { showConnectSheet = true } label: {
                    HStack(spacing: 3) { Image(systemName: "link"); Text("Connect GitHub repo") }
                        .font(.system(size: 10)).foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 5)
        .background(Color.zinc900.opacity(0.4))
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
                    Text("No elements yet. Create one (e.g. \u{201C}Inventory\u{201D}) to start collecting context.")
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
    @State private var repoPathsText = ""
    @State private var repoBranch = ""
    @State private var savingBinding = false
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
                        repoBindingSection
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
        .onAppear { initBinding() }
        .sheet(item: $previewFile) { f in AttachmentPreviewSheet(file: f) }
        .onChange(of: isCreatingFolder) { _, v in if v { folderFocused = true } }
    }

    // MARK: repository binding (git element)

    /// Glob patterns + optional branch that map local commits to this element.
    /// Editing here drives the commit-scan matcher; empty = element isn't a git
    /// binding (still usable as a plain context bucket).
    @ViewBuilder
    private var repoBindingSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                Text("REPOSITORY").font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary).tracking(0.5)
                Spacer()
                if element.hasRepoBinding {
                    let n = element.repoPaths?.count ?? 0
                    Text("\(n) path\(n == 1 ? "" : "s")")
                        .font(.system(size: 9)).foregroundColor(.matcha500)
                }
            }
            Text("Glob patterns mapping commits to this element — one per line (e.g. server/**).")
                .font(.system(size: 10)).foregroundColor(.secondary)
            TextEditor(text: $repoPathsText)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.white.opacity(0.9))
                .scrollContentBackground(.hidden)
                .frame(height: 58)
                .padding(5)
                .background(Color.zinc800.opacity(0.6)).cornerRadius(5)
            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.branch").font(.system(size: 10)).foregroundColor(.secondary)
                TextField("Branch (optional, e.g. main)", text: $repoBranch)
                    .textFieldStyle(.plain).font(.system(size: 11)).foregroundColor(.white)
                    .padding(6).background(Color.zinc800.opacity(0.6)).cornerRadius(5)
                Button { saveBinding() } label: {
                    if savingBinding { ProgressView().controlSize(.small) }
                    else { Text("Save").font(.system(size: 11, weight: .semibold)).foregroundColor(.matcha500) }
                }
                .buttonStyle(.plain).disabled(savingBinding)
            }
        }
        .padding(10)
        .background(Color.zinc900.opacity(0.4)).cornerRadius(6)
    }

    private func initBinding() {
        repoPathsText = (element.repoPaths ?? []).joined(separator: "\n")
        repoBranch = element.repoBranch ?? ""
    }

    private func saveBinding() {
        let paths = repoPathsText
            .split(whereSeparator: { $0 == "\n" || $0 == "," })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        let branch = repoBranch.trimmingCharacters(in: .whitespaces)
        savingBinding = true
        Task {
            await viewModel.updateElementRepoBinding(element, repoPaths: paths, repoBranch: branch.isEmpty ? nil : branch)
            await MainActor.run { savingBinding = false }
        }
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
                        .onTapGesture { SafeURL.open(u) }
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
        var url = newLink.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty, let pid = projectId else { return }
        // Default a bare host to https, then only persist web links — a stored
        // file:// / smb:// would later be opened by every project member.
        if let parsed = URL(string: url), parsed.scheme == nil { url = "https://" + url }
        guard SafeURL.isAllowed(url) else { return }
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
