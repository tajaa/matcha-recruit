import Foundation
import Observation

@MainActor @Observable
final class ProjectsListViewModel {
    var projects: [MWProject] = []
    var invites: [MWProjectInvite] = []
    var isLoading = false
    var isMutating = false
    var errorMessage: String?

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        // Independent errors must not hide a successfully loaded project list.
        do { projects = try await MatchaWorkService.shared.listProjects(forceRefresh: true) }
        catch { errorMessage = error.localizedDescription }
        do { invites = try await MatchaWorkService.shared.listPendingInvites() }
        catch { errorMessage = error.localizedDescription }
    }

    func respond(to invite: MWProjectInvite, accept: Bool) async {
        await mutate {
            if accept { try await MatchaWorkService.shared.acceptProjectInvite(projectId: invite.projectId) }
            else { try await MatchaWorkService.shared.declineProjectInvite(projectId: invite.projectId) }
            self.invites.removeAll { $0.id == invite.id }
        }
    }

    func mutate(_ operation: () async throws -> Void) async {
        guard !isMutating else { return }
        isMutating = true
        defer { isMutating = false }
        do { try await operation(); await load() }
        catch { errorMessage = error.localizedDescription }
    }
}
