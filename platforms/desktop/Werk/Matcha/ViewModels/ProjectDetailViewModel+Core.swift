import Foundation
import AppKit

extension ProjectDetailViewModel {

    /// Pull recent project activity from the server feed (task history,
    /// file uploads, collaborator joins) and replace the in-session list.
    /// Called on project open in addition to the existing in-session
    /// `logActivity(...)` calls (which still drive optimistic UI for the
    /// actor's own moves).
    @MainActor
    func loadProjectActivity() async {
        guard let pid = project?.id else { return }
        if let rows = try? await service.fetchProjectActivity(projectId: pid, limit: 20) {
            recentActivity = rows.compactMap(Self.mapActivity)
        }
    }

    private static func mapActivity(_ row: MWProjectActivityEntry) -> CollabActivityItem? {
        let who = row.actorName?.isEmpty == false ? row.actorName! : "Someone"
        let date = parseMWDate(row.createdAt) ?? Date()
        switch row.source {
        case "task_history":
            let event = row.string("event_type") ?? ""
            let title = row.string("task_title") ?? "a task"
            switch event {
            case "created":
                return .init(icon: "plus.circle", text: "\(who) created \(title)", timestamp: date)
            case "column_change":
                let from = row.string("from_value")?.replacingOccurrences(of: "_", with: " ").capitalized ?? "?"
                let to = row.string("to_value")?.replacingOccurrences(of: "_", with: " ").capitalized ?? "?"
                return .init(icon: "arrow.right.circle",
                             text: "\(who) moved \(title): \(from) → \(to)",
                             timestamp: date)
            case "assignee_change":
                return .init(icon: "person.circle",
                             text: "\(who) reassigned \(title)",
                             timestamp: date)
            case "deleted":
                return .init(icon: "trash.circle",
                             text: "\(who) deleted \(title)",
                             timestamp: date)
            default:
                return .init(icon: "circle", text: "\(who) \(event) \(title)", timestamp: date)
            }
        case "file_upload":
            let filename = row.string("filename") ?? "a file"
            return .init(icon: "paperclip",
                         text: "\(who) uploaded \(filename)",
                         timestamp: date)
        case "collaborator_added":
            return .init(icon: "person.badge.plus",
                         text: "\(who) was added to the project",
                         timestamp: date)
        default:
            return nil
        }
    }

    func loadProject(id: String) async {
        // Stale-while-revalidate. Switching projects paints EVERY surface
        // (header + tasks/files/folders/links/collaborators/elements) instantly
        // from the per-entity service cache instead of blanking the tabs, then
        // revalidates in the background. A cold open (no cache) does a single
        // /bundle round-trip rather than ~6 separate GETs.
        let switchingProjects = project?.id != id
        let cachedDetail = service.cachedProjectDetail(id)
        if switchingProjects {
            await MainActor.run {
                errorMessage = nil
                // Paint per-entity caches if present; cold => empty until the
                // bundle/loaders land below (never leak the prior project's data).
                tasks = service.cachedProjectTasks(id) ?? []
                files = service.cachedProjectFiles(id) ?? []
                folders = service.cachedProjectFolders(id) ?? []
                links = service.cachedProjectLinks(id) ?? []
                collaborators = service.cachedCollaborators(id) ?? []
                elements = service.cachedProjectElements(id) ?? []
                // taskFiles re-seeds from each task's embedded attachments below;
                // clear the prior project's map so ids don't bleed across projects.
                taskFiles = [:]
                recentActivity = []   // Overview's .task(id:) reloads the server feed
                if let cachedDetail {
                    project = cachedDetail
                    activeChatId = cachedDetail.chats?.first?.id
                    isLoading = false
                } else {
                    project = nil      // keeps projectLoadingView until detail lands
                    isLoading = true
                }
            }
        } else {
            await MainActor.run { isLoading = true; errorMessage = nil }
        }
        do {
            if cachedDetail != nil {
                // WARM: header already painted; revalidate detail + every entity
                // in the background (the loaders force-refresh + diff-update).
                let proj = try await service.getProjectDetail(id: id, forceRefresh: true)
                await MainActor.run {
                    guard project?.id == id else { return }
                    project = proj
                    activeChatId = proj.chats?.first?.id
                    isLoading = false
                }
                Task { await self.loadTasks() }
                Task { await self.loadFiles() }
                Task { await self.loadCollaborators() }
                Task { await self.loadElements() }
            } else {
                // COLD: one /bundle call warms detail + all six sub-resources.
                // Fall back to the pre-bundle path (detail + parallel loaders) if
                // the endpoint is unavailable (older server) or fails.
                var bundle: MWProjectBundle?
                do {
                    bundle = try await service.getProjectBundle(id: id)
                } catch is CancellationError {
                    await MainActor.run { isLoading = false }
                    return
                } catch {
                    bundle = nil
                }
                if let bundle {
                    await MainActor.run {
                        project = bundle.project
                        activeChatId = bundle.project.chats?.first?.id
                        tasks = bundle.tasks
                        var seeded: [String: [MWProjectFile]] = [:]
                        for t in bundle.tasks { if let atts = t.attachments { seeded[t.id] = atts } }
                        taskFiles = seeded
                        files = bundle.files
                        folders = bundle.folders
                        links = bundle.links
                        collaborators = bundle.collaborators
                        elements = bundle.elements
                        // Bundle already returned files+folders+links fresh — stamp
                        // so the first Files/Media open doesn't redundantly refetch
                        // (chat-sync is left unstamped so Media still backfills once).
                        lastFilesFetch[id] = Date()
                        lastLinksFetch[id] = Date()
                        isLoading = false
                    }
                } else {
                    let proj = try await service.getProjectDetail(id: id, forceRefresh: true)
                    await MainActor.run {
                        project = proj
                        activeChatId = proj.chats?.first?.id
                        isLoading = false
                    }
                    Task { await self.loadTasks() }
                    Task { await self.loadFiles() }
                    Task { await self.loadCollaborators() }
                    Task { await self.loadElements() }
                }
            }
        } catch is CancellationError {
            // Rapid project switch cancelled the in-flight load. Don't show
            // a red banner — the new project's .task is already loading.
            await MainActor.run { isLoading = false }
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                await MainActor.run { isLoading = false }
                return
            }
            await MainActor.run { errorMessage = error.localizedDescription; isLoading = false }
        }
    }

    /// Refetch project without touching activeChatId or isLoading. Called when
    /// a child chat stream completes and may have mutated sections / posting /
    /// blog data on the server. Using loadProject here would reset activeChatId
    /// and flicker the loading state.
    func refreshProject() async {
        guard let pid = project?.id else { return }
        do {
            let proj = try await service.getProjectDetail(id: pid)
            await MainActor.run { project = proj }
        } catch {
            // Silent — background refresh; don't clobber user-facing errors.
        }
    }

    func addSection(title: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.addProjectSection(projectId: pid, title: title)
            await MainActor.run {
                project = updated
                logActivity("text.append", "added section \u{201C}\(title)\u{201D}")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func updateSection(sectionId: String, title: String? = nil, content: String? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectSection(projectId: pid, sectionId: sectionId, title: title, content: content)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteSection(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.deleteProjectSection(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func acceptSectionRevision(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.acceptProjectSectionRevision(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func rejectSectionRevision(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.rejectProjectSectionRevision(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func createChat(title: String?) async {
        guard let pid = project?.id else { return }
        do {
            let thread = try await service.createProjectChat(projectId: pid, title: title)
            await MainActor.run {
                activeChatId = thread.id
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Rename the project. Server returns the updated MWProject; we apply it
    /// directly so the UI reflects the new title without an extra GET.
    /// `updateProjectMeta` invalidates the project list cache, so the sidebar
    /// shows the new title on next render too.
    func updateTitle(_ newTitle: String) async {
        guard let pid = project?.id else { return }
        let trimmed = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        // Optimistic — patch the local detail title and tell the sidebar to
        // patch its row in place. Server roundtrip happens after; on failure
        // we revert and re-emit.
        let previous = project?.title
        await MainActor.run {
            project?.title = trimmed
            if let prev = previous, prev != trimmed {
                logActivity("pencil", "renamed to \u{201C}\(trimmed)\u{201D}")
            }
        }
        NotificationCenter.default.post(
            name: .mwProjectTitlePatched,
            object: MWProjectTitlePatch(id: pid, title: trimmed)
        )
        do {
            let updated = try await service.updateProjectMeta(id: pid, title: trimmed)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run {
                if let previous { project?.title = previous }
                errorMessage = error.localizedDescription
            }
            if let previous {
                NotificationCenter.default.post(
                    name: .mwProjectTitlePatched,
                    object: MWProjectTitlePatch(id: pid, title: previous)
                )
            }
        }
    }

    /// Toggle sales-pipeline mode for the current project. Persists to
    /// project_data.pipeline_mode (merged server-side) and refreshes the local
    /// project so the kanban board re-renders with sales stages + deal fields.
    func setPipelineMode(_ enabled: Bool) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.setPipelineMode(projectId: pid, enabled: enabled)
            await MainActor.run { self.project = updated }
        } catch {
            await MainActor.run { self.errorMessage = "Failed to update pipeline mode" }
        }
    }

    /// Change the project's sidebar/header icon (SF Symbol name). Optimistic:
    /// paints the new icon immediately; on failure surfaces an error and the
    /// next project load revalidates from the server.
    func setProjectIcon(_ icon: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run { project?.icon = icon }
        do {
            _ = try await service.updateProjectMeta(id: pid, icon: icon)
        } catch {
            await MainActor.run { errorMessage = "Failed to update icon" }
        }
    }

    func exportProject(format: String) async -> Data? {
        guard let pid = project?.id else { return nil }
        do {
            return try await service.exportProject(projectId: pid, format: format)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }
}
