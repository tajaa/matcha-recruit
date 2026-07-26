import Foundation
import AppKit

extension ProjectDetailViewModel {

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
            await refreshProject()
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
            await refreshProject()
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
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func syncProjectInterviews() async {
        guard let pid = project?.id else { return }
        do {
            try await service.syncProjectInterviews(projectId: pid)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func analyzeProjectCandidates() async {
        guard let pid = project?.id else { return }
        do {
            try await service.analyzeProjectCandidates(projectId: pid)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func rejectCandidate(candidateId: String, reason: String?, sendEmail: Bool) async {
        guard let pid = project?.id else { return }
        do {
            try await service.rejectProjectCandidate(projectId: pid, candidateId: candidateId, reason: reason, sendEmail: sendEmail)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Discipline

    func patchDiscipline(_ patch: MatchaWorkService.MWDisciplinePatch) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchDiscipline(projectId: pid, patch: patch)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func confirmDisciplineMeetingHeld() async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.markDisciplineMeetingHeld(projectId: pid)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func requestDisciplineSignature(employeeEmail: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.requestDisciplineSignature(projectId: pid, employeeEmail: employeeEmail)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func refuseDisciplineSignature(notes: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.refuseDisciplineSignature(projectId: pid, notes: notes)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadDisciplinePhysicalSignature(fileURL: URL) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.uploadDisciplinePhysicalSignature(projectId: pid, fileURL: fileURL)
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
