import Foundation
import AppKit
import UniformTypeIdentifiers

extension ProjectDetailViewModel {

    // MARK: - Collab: files

    func loadFiles() async {
        guard let pid = project?.id else { return }
        // Spinner only on a cold load; a warm revalidate diff-updates in place.
        let wasEmpty = files.isEmpty && folders.isEmpty
        await MainActor.run { if wasEmpty { isLoadingFiles = true } }
        do {
            // Files + folders concurrently (was serial → doubled the latency).
            async let filesReq = service.listProjectFiles(projectId: pid, forceRefresh: true)
            async let foldersReq = service.listProjectFolders(projectId: pid, forceRefresh: true)
            let list = try await filesReq
            let fetchedFolders = try? await foldersReq
            await MainActor.run {
                guard project?.id == pid else { return }
                files = list
                if let fetchedFolders { folders = fetchedFolders }
                isLoadingFiles = false
                lastFilesFetch[pid] = Date()
            }
        } catch is CancellationError {
            await MainActor.run { isLoadingFiles = false }
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                await MainActor.run { isLoadingFiles = false }
                return
            }
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoadingFiles = false
            }
        }
    }

    /// Backfill Files/Media with chat attachments (screenshots dropped in chat),
    /// then reload if anything was added. Idempotent + best-effort.
    func syncChatFiles() async {
        guard let pid = project?.id else { return }
        // Stamp up front so concurrent re-entries throttle even mid-sync.
        await MainActor.run { lastChatSyncFetch[pid] = Date() }
        if let added = try? await service.syncChatFiles(projectId: pid), added > 0 {
            await loadFiles()
        }
    }

    /// Links shared in the collab chat (URLs parsed from messages). Best-effort:
    /// failures leave the previous list intact rather than surfacing an error.
    func loadLinks() async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listProjectLinks(projectId: pid, forceRefresh: true) {
            await MainActor.run {
                guard project?.id == pid else { return }
                links = list
                lastLinksFetch[pid] = Date()
            }
        }
    }

    /// Files-tab onAppear: never blank — paint from current state, revalidate
    /// only when empty or the last fetch is stale (>30s). Replaces the old
    /// unconditional per-entry refetch; the service cache + WS keep data fresh.
    func ensureFilesFresh() async {
        guard let pid = project?.id else { return }
        if files.isEmpty && folders.isEmpty { await loadFiles(); return }
        if !isFresh(lastFilesFetch, pid) { await loadFiles() }
    }

    /// Media-tab onAppear: files + (throttled) chat-file sync + links. Collapses
    /// the old always-3-network-calls-per-entry into throttled first-entry work.
    func ensureMediaFresh() async {
        guard let pid = project?.id else { return }
        await ensureFilesFresh()
        if !isFresh(lastChatSyncFetch, pid) { Task { await self.syncChatFiles() } }
        if !isFresh(lastLinksFetch, pid) { Task { await self.loadLinks() } }
    }

    func uploadFile(data: Data, filename: String, mimeType: String) async {
        guard let pid = project?.id else { return }
        do {
            let uploaded = try await service.uploadProjectFile(
                projectId: pid, file: (data: data, filename: filename, mimeType: mimeType)
            )
            await MainActor.run {
                files.insert(uploaded, at: 0)
                logActivity("doc.fill", "uploaded \(filename)")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadFile(data: Data, filename: String, mimeType: String, folderId: String) async {
        let countBefore = files.count
        await uploadFile(data: data, filename: filename, mimeType: mimeType)
        guard files.count > countBefore,
              let file = files.first(where: { $0.folderId == nil && $0.filename == filename })
        else { return }
        await moveFile(id: file.id, toFolder: folderId)
    }

    func deleteFile(id: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run { files.removeAll { $0.id == id } }
        do {
            try await service.deleteProjectFile(projectId: pid, fileId: id)
        } catch {
            await loadFiles()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Collab: file folders

    func loadFolders() async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listProjectFolders(projectId: pid, forceRefresh: true) {
            await MainActor.run {
                guard project?.id == pid else { return }
                folders = list
            }
        }
    }

    @discardableResult
    func createFolder(name: String, parentId: String? = nil) async -> MWProjectFolder? {
        guard let pid = project?.id else { return nil }
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let folder = try await service.createProjectFolder(projectId: pid, name: clean, parentId: parentId)
            await MainActor.run {
                folders.append(folder)
                folders.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            }
            return folder
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    func renameFolder(id: String, name: String) async {
        guard let pid = project?.id else { return }
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let updated = try await service.renameProjectFolder(projectId: pid, folderId: id, name: clean)
            await MainActor.run {
                if let idx = folders.firstIndex(where: { $0.id == id }) { folders[idx] = updated }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteFolder(id: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            folders.removeAll { $0.id == id }
            // Files in the deleted folder fall back to the root (matches the
            // backend's ON DELETE SET NULL).
            for i in files.indices where files[i].folderId == id { files[i].folderId = nil }
        }
        do {
            try await service.deleteProjectFolder(projectId: pid, folderId: id)
        } catch {
            await loadFiles()
            await loadFolders()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Move a file into a folder, or to the root when folderId is nil.
    func moveFile(id: String, toFolder folderId: String?) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            if let idx = files.firstIndex(where: { $0.id == id }) { files[idx].folderId = folderId }
        }
        do {
            _ = try await service.moveProjectFile(projectId: pid, fileId: id, folderId: folderId)
        } catch {
            await loadFiles()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Copy a file into a folder, leaving the original at root. The original
    /// keeps `folderId == nil` (stays in Media); the returned copy carries the
    /// folderId (shows in the Files tab under that folder).
    func copyFileToFolder(id: String, toFolder folderId: String) async {
        guard let pid = project?.id else { return }
        do {
            let copy = try await service.copyProjectFile(projectId: pid, fileId: id, folderId: folderId)
            await MainActor.run {
                if !files.contains(where: { $0.id == copy.id }) { files.insert(copy, at: 0) }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}

// MARK: - Export save panel (free function so ProjectDetailView.swift stays short)

@MainActor
func presentExportSavePanel(data: Data, format: String, title: String) {
    let panel = NSSavePanel()
    panel.nameFieldStringValue = "\(title).\(format)"
    switch format {
    case "pdf":
        panel.allowedContentTypes = [.pdf]
    case "docx":
        if let t = UTType(filenameExtension: "docx") { panel.allowedContentTypes = [t] }
    case "md":
        if let t = UTType(filenameExtension: "md") { panel.allowedContentTypes = [t] }
    default:
        break
    }
    Task {
        let response: NSApplication.ModalResponse
        if let window = NSApp.keyWindow ?? NSApp.mainWindow {
            response = await panel.beginSheetModal(for: window)
        } else {
            response = await panel.begin()
        }
        guard response == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url)
        } catch {
            // Previously print-only — the user got no signal the export failed.
            print("[Export] write failed: \(error)")
            let alert = NSAlert()
            alert.messageText = "Export failed"
            alert.informativeText = "Couldn't write \(url.lastPathComponent). \(error.localizedDescription)"
            alert.alertStyle = .warning
            if let window = NSApp.keyWindow ?? NSApp.mainWindow {
                alert.beginSheetModal(for: window, completionHandler: nil)
            } else {
                alert.runModal()
            }
        }
    }
}
