import Foundation

@Observable
class ProjectDetailViewModel {
    var project: MWProject?
    var chats: [MWThread] = []
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
                isLoading = false
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription; isLoading = false }
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
