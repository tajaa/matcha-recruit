import Foundation
import AppKit

extension ProjectDetailViewModel {

    func loadCollaborators() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listCollaborators(projectId: pid, forceRefresh: true)
            await MainActor.run {
                guard project?.id == pid else { return }
                collaborators = list
            }
        } catch is CancellationError {
            return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                return
            }
            // Silent — picker just shows "Unassigned"; don't red-banner.
        }
    }

    // MARK: - Elements

    func loadElements() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listProjectElements(projectId: pid, forceRefresh: true)
            await MainActor.run {
                guard project?.id == pid else { return }
                elements = list
            }
        } catch is CancellationError { return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        }
    }

    @discardableResult
    func createElement(name: String, kind: String?, description: String?, assignedTo: String?) async -> MWProjectElement? {
        guard let pid = project?.id else { return nil }
        do {
            let el = try await service.createProjectElement(
                projectId: pid, name: name, kind: kind,
                description: description, assignedTo: assignedTo
            )
            await MainActor.run { elements.append(el) }
            return el
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    func updateElement(_ element: MWProjectElement, name: String?, kind: String?, description: String?, assignedTo: String?) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectElement(
                projectId: pid, elementId: element.id,
                name: name, kind: kind,
                description: description, assignedTo: assignedTo
            )
            await MainActor.run {
                if let i = elements.firstIndex(where: { $0.id == element.id }) {
                    elements[i] = updated
                }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteElement(_ element: MWProjectElement) async {
        guard let pid = project?.id else { return }
        await MainActor.run { elements.removeAll { $0.id == element.id } }
        do {
            try await service.deleteProjectElement(projectId: pid, elementId: element.id)
        } catch {
            await loadElements()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Save an element's git repo binding (path globs + optional branch pin).
    func updateElementRepoBinding(_ element: MWProjectElement, repoPaths: [String], repoBranch: String?) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectElement(
                projectId: pid, elementId: element.id,
                repoPaths: repoPaths, repoBranch: repoBranch ?? ""
            )
            await MainActor.run {
                if let i = elements.firstIndex(where: { $0.id == element.id }) { elements[i] = updated }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - GitHub connection + commit scanning

    var isGitHubConnected: Bool { !(project?.githubRepo ?? "").isEmpty }
    var connectedGitHubRepo: String? { project?.githubRepo }
    var connectedGitHubBranch: String? { project?.githubBranch }

    /// Connect / change the project's GitHub repo (validated server-side).
    /// `repo` is owner/name; empty disconnects.
    func connectGitHubRepo(repo: String, branch: String?) async {
        guard let pid = project?.id else { return }
        do {
            let conn = try await service.setGitHubConnection(projectId: pid, repo: repo, branch: branch)
            await MainActor.run {
                project?.githubRepo = conn.repo
                project?.githubBranch = conn.branch
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func disconnectGitHubRepo() async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.setGitHubConnection(projectId: pid, repo: "", branch: nil)
            await MainActor.run {
                project?.githubRepo = nil
                project?.githubBranch = nil
                lastScanSummary = nil
                lastSyncSummary = nil
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// 1-click AI catch-up summary for a ticket. Stores the result in
    /// `taskSummaries[taskId]`; on failure stores a soft retry message so the
    /// UI always shows something.
    /// `projectId` should be the ticket's own `project_id` (always populated on
    /// the task payload) — the viewer can be driven by a VM whose `project`
    /// hasn't loaded (Home, split panes, embedded boards), and the old
    /// `guard let pid = project?.id` path returned SILENTLY there: no request,
    /// no message, sparkle button looked dead. Fall back to the VM project only
    /// when no explicit id is passed.
    func summarizeTask(taskId: String, projectId: String? = nil) async {
        guard let pid = projectId ?? project?.id else {
            await MainActor.run {
                taskSummaries[taskId] = "Couldn't generate a summary — missing project context."
            }
            return
        }
        do {
            let summary = try await service.summarizeTask(projectId: pid, taskId: taskId)
            await MainActor.run { taskSummaries[taskId] = summary }
        } catch {
            print("[summarizeTask] failed project=\(pid) task=\(taskId): \(error)")
            await MainActor.run {
                taskSummaries[taskId] = "Couldn't generate a summary right now — try again."
            }
        }
    }

    /// Refresh pending suggestions from the server (e.g. on project open).
    func loadCommitSuggestions() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listCommitSuggestions(projectId: pid)
            await MainActor.run { regroupSuggestions(list) }
        } catch { /* non-fatal — suggestions are advisory */ }
    }

    /// Replace the keyed suggestion map from a flat list (server is source of truth).
    private func regroupSuggestions(_ list: [MWCommitSuggestion]) {
        commitSuggestions = Dictionary(grouping: list, by: { $0.taskId })
    }

    /// Pending suggestions for one subtask (used by the checklist chip).
    func suggestions(taskId: String, subtaskId: String) -> [MWCommitSuggestion] {
        (commitSuggestions[taskId] ?? []).filter { $0.subtaskId == subtaskId && $0.status == "pending" }
    }

    func loadCommitCompletions(taskId: String) async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listCommitCompletions(projectId: pid, taskId: taskId) {
            await MainActor.run {
                commitCompletions = Dictionary(list.map { ($0.subtaskId, $0) },
                                               uniquingKeysWith: { a, _ in a })
            }
        }
    }

    /// Which commit completed this subtask (nil if none / human-completed).
    func completion(subtaskId: String) -> MWCommitSuggestion? { commitCompletions[subtaskId] }

    /// How many distinct subtasks on a task a commit may have completed (still
    /// pending accept) — drives the kanban card badge. Distinct on subtask_id so
    /// two commits hitting the same subtask count once.
    func pendingSuggestionCount(taskId: String) -> Int {
        let pending = (commitSuggestions[taskId] ?? []).filter { $0.status == "pending" }
        return Set(pending.map { $0.subtaskId }).count
    }

    func acceptSuggestion(_ s: MWCommitSuggestion) async {
        guard let pid = project?.id else { return }
        // Optimistic: drop the chip and tick the box locally.
        await MainActor.run {
            commitSuggestions[s.taskId]?.removeAll { $0.id == s.id }
            if var list = taskSubtasks[s.taskId], let i = list.firstIndex(where: { $0.id == s.subtaskId }) {
                list[i].isDone = true
                taskSubtasks[s.taskId] = list
                syncSubtaskCounts(taskId: s.taskId)
            }
        }
        do {
            try await service.acceptCommitSuggestion(projectId: pid, suggestionId: s.id)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            await loadSubtasks(taskId: s.taskId)
            await loadCommitSuggestions()
        }
    }

    func dismissSuggestion(_ s: MWCommitSuggestion) async {
        guard let pid = project?.id else { return }
        await MainActor.run { commitSuggestions[s.taskId]?.removeAll { $0.id == s.id } }
        do {
            try await service.dismissCommitSuggestion(projectId: pid, suggestionId: s.id)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            await loadCommitSuggestions()
        }
    }

    /// Pull element code from GitHub (server-side, read-only token) — no local
    /// clone or bookmark needed, works for any collaborator.
    func syncFromGitHub() async {
        guard let pid = project?.id else { return }
        if elements.isEmpty { await loadElements() }
        await MainActor.run { isSyncingRepo = true }
        do {
            let res = try await service.syncFromGitHub(projectId: pid)
            lastGitHubSyncAt[pid] = Date()
            await MainActor.run {
                isSyncingRepo = false
                lastSyncSummary = "GitHub: \(res.totalStored) files" + (res.repo.map { " · \($0)" } ?? "")
            }
        } catch {
            await MainActor.run { isSyncingRepo = false; errorMessage = error.localizedDescription }
        }
    }

    /// Auto-sync on Props-tab open, gated so it can't spam GitHub:
    ///  1. skip if a sync is already running (no concurrent calls)
    ///  2. skip if synced within the cooldown window (per project)
    ///  3. skip if no element has globs bound (nothing to fetch)
    /// Silent on failure (no error banner) — the manual button surfaces errors
    /// and bypasses the cooldown.
    func autoSyncFromGitHubIfStale() async {
        guard let pid = project?.id, !isSyncingRepo, isGitHubConnected else { return }
        if let last = lastGitHubSyncAt[pid], Date().timeIntervalSince(last) < githubSyncCooldown { return }
        if elements.isEmpty { await loadElements() }
        guard elements.contains(where: { !($0.repoPaths ?? []).isEmpty }) else { return }
        // Stamp BEFORE the await so a rapid second .task firing can't double-fire.
        lastGitHubSyncAt[pid] = Date()
        await MainActor.run { isSyncingRepo = true }
        do {
            let res = try await service.syncFromGitHub(projectId: pid)
            await MainActor.run { isSyncingRepo = false; lastSyncSummary = "GitHub: \(res.totalStored) files" }
        } catch {
            await MainActor.run { isSyncingRepo = false }  // silent on auto; keep the stamp so a failure doesn't retry-spam
        }
    }

    /// Manual "Scan commits": force a re-scan of recent commits (so a just-added
    /// ticket can match already-merged work). Chips appear on tickets.
    func scanCommitsFromGitHub() async {
        guard let pid = project?.id, !isScanningCommits else { return }
        await MainActor.run { isScanningCommits = true }
        do {
            let r = try await service.scanCommitsFromGitHub(projectId: pid, force: true)
            lastGitHubScanAt[pid] = Date()
            await MainActor.run {
                isScanningCommits = false
                regroupSuggestions(r.suggestions)
                lastScanSummary = "\(r.scanned) commit\(r.scanned == 1 ? "" : "s") · \(r.suggestions.count) suggestion\(r.suggestions.count == 1 ? "" : "s")"
            }
            // High-confidence matches auto-check subtasks server-side — refresh
            // task aggregates so card progress (X/Y) reflects them.
            if r.scanned > 0 { await loadTasks() }
        } catch {
            await MainActor.run { isScanningCommits = false; errorMessage = error.localizedDescription }
        }
    }

    /// Auto-scan the connected branch on Kanban open — gated so it "just happens"
    /// after you merge without spamming GitHub. Gates: not already scanning,
    /// 10-min per-project cooldown, repo connected. Silent on failure (the manual
    /// Scan button surfaces errors and bypasses the cooldown).
    func autoScanCommitsIfStale() async {
        guard let pid = project?.id, !isScanningCommits, isGitHubConnected else { return }
        if let last = lastGitHubScanAt[pid], Date().timeIntervalSince(last) < githubSyncCooldown { return }
        lastGitHubScanAt[pid] = Date()  // stamp before the await so a re-fire skips
        await MainActor.run { isScanningCommits = true }
        do {
            // Watermark scan: only NEW commits since the last scan (cheap).
            let r = try await service.scanCommitsFromGitHub(projectId: pid, force: false)
            await MainActor.run {
                isScanningCommits = false
                regroupSuggestions(r.suggestions)
                if !r.suggestions.isEmpty {
                    lastScanSummary = "\(r.scanned) commit\(r.scanned == 1 ? "" : "s") · \(r.suggestions.count) suggestion\(r.suggestions.count == 1 ? "" : "s")"
                }
            }
            // Reflect any server-side auto-checks (high-confidence matches).
            if r.scanned > 0 { await loadTasks() }
        } catch {
            await MainActor.run { isScanningCommits = false }  // silent on auto
        }
    }

    /// Register the GitHub push webhook so a merge auto-triggers a scan (no polling).
    func installGitHubWebhook() async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.installGitHubWebhook(projectId: pid)
            await MainActor.run { lastScanSummary = "Push auto-scan enabled" }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}
