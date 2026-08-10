import Foundation
import Observation

@MainActor @Observable
final class ProjectsListViewModel {
    var projects: [MWProject] = []
    var isLoading = false
    var errorMessage: String?

    func load() async {
        isLoading = projects.isEmpty
        defer { isLoading = false }
        do {
            projects = try await MatchaWorkService.shared.listProjects()
                .filter { $0.projectType == MWProjectType.collab.rawValue }
        } catch { errorMessage = error.localizedDescription }
    }
}
