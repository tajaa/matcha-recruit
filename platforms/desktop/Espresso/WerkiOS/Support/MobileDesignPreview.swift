#if DEBUG
import SwiftUI

/// Non-interactive, network-free visual fixtures; absent from Release builds.
/// Launch with -espresso-preview; appearance and accessibility flags are below.
struct MobileDesignPreview: View {
    private let args = ProcessInfo.processInfo.arguments
    var body: some View {
        Group {
            if args.contains("-project") {
                NavigationStack { CollabProjectView(projectId: "studio", previewVM: Self.projectVM()) }
            } else if args.contains("-login") {
                LoginView()
            } else {
                TabView {
                    ProjectsListView(previewProjects: Self.projects).tabItem { Label("Projects", systemImage: "square.grid.2x2") }
                    Text("Channels").tabItem { Label("Channels", systemImage: "number") }
                    Text("Messages").tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }
                }
            }
        }.preferredColorScheme(args.contains("-dark") ? .dark : .light)
            .environment(\.dynamicTypeSize, args.contains("-large") ? .accessibility2 : .large)
    }

    static var projects: [MWProject] {
        decode(#"""
        [
          {"id":"studio","title":"The Sunday Studio","project_type":"collab","status":"active","is_pinned":true,"icon":"paintbrush","collaborator_role":"owner","updated_at":"2026-09-19T12:00:00Z"},
          {"id":"personal","title":"Little things, big ideas","project_type":"general","status":"active","icon":"lightbulb","collaborator_role":"owner","updated_at":"2026-09-18T12:00:00Z"},
          {"id":"launch","title":"Autumn launch","project_type":"collab","status":"active","icon":"leaf","collaborator_role":"owner","updated_at":"2026-09-17T12:00:00Z"}
        ]
        """#)
    }
    static func projectVM() -> ProjectDetailViewModel {
        let vm = ProjectDetailViewModel()
        vm.project = projects[0]
        vm.tasks = decode(#"""
        [
          {"id":"brief","title":"Shape the creative brief","board_column":"todo","priority":"high","status":"pending","assigned_name":"Alex","due_date":"2026-09-24","subtask_total":4,"subtask_done":1},
          {"id":"mood","title":"Collect a little inspiration","board_column":"todo","priority":"medium","status":"pending","assigned_name":"Jamie"},
          {"id":"identity","title":"Explore the visual identity","board_column":"in_progress","priority":"medium","status":"in_progress","assigned_name":"Alex","subtask_total":3,"subtask_done":2},
          {"id":"kickoff","title":"A good beginning: team kickoff","board_column":"done","priority":"low","status":"completed"}
        ]
        """#)
        return vm
    }
    private static func decode<T: Decodable>(_ json: String) -> T {
        // Static fixture corruption should fail immediately during development.
        try! JSONDecoder().decode(T.self, from: Data(json.utf8))
    }
}
#endif
