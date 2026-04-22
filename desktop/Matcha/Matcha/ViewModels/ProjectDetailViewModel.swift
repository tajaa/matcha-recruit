import Foundation

@Observable
class ProjectDetailViewModel {
    var project: MWProject?
    var activeChatId: String?
    var isLoading = false
    var errorMessage: String?

    private let service = MatchaWorkService.shared

    func loadProject(id: String) async {
        await MainActor.run { isLoading = true; errorMessage = nil }
        do {
            let proj = try await service.getProjectDetail(id: id)
            await MainActor.run {
                project = proj
                // Always pick up the loaded project's first chat. The VM is
                // persistent @State on ProjectDetailView, so switching to a
                // different project (or creating a new one) reuses the same
                // instance. Without this reset, activeChatId from the previous
                // project leaks in, and chatVM renders the old project's
                // chat in the new project's editor.
                activeChatId = proj.chats?.first?.id
                isLoading = false
            }
        } catch {
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
            await MainActor.run { project = updated }
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

    // MARK: - Recruiting

    var recruitingData: MWRecruitingData {
        MWRecruitingData.from(projectData: project?.projectData)
    }

    /// Replace one array key inside the live `project.projectData` blob.
    /// Triggers a reactive re-render via @Observable since `MWRecruitingData`
    /// is recomputed from `projectData` on every access.
    @MainActor
    private func setProjectDataIds(_ key: String, _ ids: [String]) {
        guard var data = project?.projectData else { return }
        data[key] = AnyCodable(ids.map { AnyCodable($0) })
        project?.projectData = data
    }

    func toggleShortlist(candidateId: String) async {
        guard let pid = project?.id else { return }
        let priorIds = recruitingData.shortlistIds
        let wasIn = priorIds.contains(candidateId)
        var next = priorIds
        if wasIn { next.remove(candidateId) } else { next.insert(candidateId) }
        await setProjectDataIds("shortlist_ids", Array(next).sorted())
        do {
            _ = try await service.toggleShortlist(projectId: pid, candidateId: candidateId)
        } catch {
            await setProjectDataIds("shortlist_ids", Array(priorIds).sorted())
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func toggleDismiss(candidateId: String) async {
        guard let pid = project?.id else { return }
        let priorIds = recruitingData.dismissedIds
        let wasIn = priorIds.contains(candidateId)
        var next = priorIds
        if wasIn { next.remove(candidateId) } else { next.insert(candidateId) }
        await setProjectDataIds("dismissed_ids", Array(next).sorted())
        do {
            _ = try await service.toggleProjectDismiss(projectId: pid, candidateId: candidateId)
        } catch {
            await setProjectDataIds("dismissed_ids", Array(priorIds).sorted())
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func savePosting(title: String?, content: String, finalized: Bool) async {
        guard let pid = project?.id else { return }
        let payload: [String: Any] = [
            "title": title ?? project?.title ?? "",
            "content": content,
            "finalized": finalized,
        ]
        do {
            _ = try await service.updateProjectPosting(projectId: pid, posting: payload)
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadProjectResumes(files: [(data: Data, filename: String, mimeType: String)]) async {
        guard let pid = project?.id else { return }
        do {
            let bytes = try await service.uploadProjectResumes(projectId: pid, files: files)
            for try await line in bytes.lines {
                if line.hasPrefix("data: "),
                   line.contains("\"type\":\"complete\"") || line.contains("[DONE]") {
                    break
                }
            }
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func sendProjectInterviews(candidateIds: [String], positionTitle: String?, customMessage: String?) async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.sendProjectInterviews(
                projectId: pid,
                candidateIds: candidateIds,
                positionTitle: positionTitle,
                customMessage: customMessage
            )
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func syncProjectInterviews() async {
        guard let pid = project?.id else { return }
        do {
            try await service.syncProjectInterviews(projectId: pid)
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func analyzeProjectCandidates() async {
        guard let pid = project?.id else { return }
        do {
            try await service.analyzeProjectCandidates(projectId: pid)
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func rejectCandidate(candidateId: String, reason: String?, sendEmail: Bool) async {
        guard let pid = project?.id else { return }
        do {
            try await service.rejectProjectCandidate(projectId: pid, candidateId: candidateId, reason: reason, sendEmail: sendEmail)
            await loadProject(id: pid)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
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

    // MARK: - Consultation

    var consultationData: MWConsultationData {
        MWConsultationData.from(projectData: project?.projectData)
    }

    func patchConsultation(
        clientProfile: MWConsultationClient? = nil,
        engagement: MWEngagement? = nil,
        stage: String? = nil,
        tags: [String]? = nil,
        customFields: [MWCustomField]? = nil
    ) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchConsultation(
                id: pid,
                clientProfile: clientProfile,
                engagement: engagement,
                stage: stage,
                tags: tags,
                customFields: customFields
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func appendSession(
        at: String?,
        durationMin: Int?,
        notes: String?,
        billable: Bool,
        rateCentsOverride: Int? = nil,
        linkedThreadId: String? = nil
    ) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.appendSession(
                projectId: pid, at: at, durationMin: durationMin, notes: notes,
                billable: billable, rateCentsOverride: rateCentsOverride,
                linkedThreadId: linkedThreadId
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func updateSession(sessionId: String, at: String? = nil, durationMin: Int? = nil, notes: String? = nil, billable: Bool? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateSession(
                projectId: pid, sessionId: sessionId,
                at: at, durationMin: durationMin, notes: notes, billable: billable
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteSession(sessionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.deleteSession(projectId: pid, sessionId: sessionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func addActionItem(text: String, sourceThreadId: String? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.addActionItem(
                projectId: pid, text: text, sourceThreadId: sourceThreadId
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func toggleActionItem(itemId: String, completed: Bool) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchActionItem(
                projectId: pid, itemId: itemId, completed: completed
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func confirmActionItem(itemId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchActionItem(
                projectId: pid, itemId: itemId, pendingConfirmation: false
            )
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func dismissActionItem(itemId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.deleteActionItem(projectId: pid, itemId: itemId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Blog

    var blogData: MWBlogData {
        MWBlogData.from(projectData: project?.projectData)
    }

    func patchBlog(_ patch: MWBlogPatchRequest) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchBlog(id: pid, patch: patch)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func transitionBlogStatus(to status: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.transitionBlogStatus(id: pid, status: status)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func exportBlogMarkdown() async -> Data? {
        guard let pid = project?.id else { return nil }
        do {
            return try await service.exportProject(projectId: pid, format: "md_frontmatter")
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }
}
