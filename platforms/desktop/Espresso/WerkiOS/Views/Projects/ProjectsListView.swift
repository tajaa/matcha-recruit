import SwiftUI

struct ProjectsListView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = ProjectsListViewModel()

    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading { ProgressView() }
                else if vm.projects.isEmpty { ContentUnavailableView("No projects", systemImage: "square.grid.2x2", description: Text(vm.errorMessage ?? "Your collab projects will appear here.")) }
                else { List(vm.projects) { project in
                    NavigationLink { CollabProjectView(projectId: project.id) } label: {
                        HStack { Image(systemName: project.icon ?? "square.grid.2x2"); VStack(alignment: .leading) { Text(project.title).fontWeight(.semibold); Text(project.status ?? "Active").font(.caption).foregroundStyle(.secondary) } }
                    }
                }.refreshable { await vm.load() } }
            }
            .navigationTitle("Projects")
        }
        .task { await vm.load() }
    }
}
