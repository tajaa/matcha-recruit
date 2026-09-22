import Foundation

/// Fast host-side checks of the real shared models + mobile rules. No live API,
/// credentials, simulator, stubs, or production data are used.
@main struct MobileProjectRulesTests {
    static func main() throws {
        let data = Data(#"""
        [
          {"id":"solo","title":"Café ideas ☕️","project_type":"general","status":"active","updated_at":"2026-09-19T12:00:00Z"},
          {"id":"team","title":"Studio launch","project_type":"collab","status":"active","is_pinned":true,"updated_at":"2026-09-18T12:00:00Z"},
          {"id":"old","title":"Archive","project_type":"general","status":"archived"},
          {"id":"slides","title":"Deck","project_type":"presentation","status":"active"},
          {"id":"legacy","title":"Legacy","status":"active"},
          {"id":"finished","title":"Finished","project_type":"collab","status":"completed"}
        ]
        """#.utf8)
        let projects = try JSONDecoder().decode([MWProject].self, from: data)
        var checks = 0
        func check(_ condition: @autoclosure () -> Bool, _ message: String) {
            guard condition() else { fatalError(message) }
            checks += 1
        }
        func ids(_ filter: MobileProjectFilter, _ query: String = "") -> [String] {
            MobileProjectRules.visibleProjects(projects, filter: filter, query: query).map(\.id)
        }
        check(ids(.all).first == "team", "Pinned projects sort first")
        check(Set(ids(.all)) == Set(["solo", "team", "legacy", "finished"]), "Mobile excludes archived and specialist projects")
        check(Set(ids(.solo)) == Set(["solo", "legacy"]), "Solo includes legacy default type")
        check(Set(ids(.collab)) == Set(["team", "finished"]), "Collab retains completed projects")
        check(ids(.archived) == ["old"], "Archive is recoverable")
        check(ids(.all, "  CAFÉ  ") == ["solo"], "Case-insensitive trimmed Unicode search")
        check(ids(.all, "☕️") == ["solo"], "Emoji search")
        check(ids(.all, "missing").isEmpty, "No match")
        check(ids(.all, "  ") == ids(.all), "Empty search")
        var project = projects[0]
        for role in ["viewer", "commenter"] {
            project.collaboratorRole = role
            check(!project.mobileCanEdit && !project.mobileIsOwner, "Read-only role cannot mutate")
        }
        project.collaboratorRole = "collaborator"
        check(project.mobileCanEdit && !project.mobileIsOwner, "Collaborator cannot manage roster")
        project.collaboratorRole = "owner"
        check(project.mobileCanEdit && project.mobileIsOwner, "Owner actions")
        for day in ["2026-03-08", "2026-11-01", "2028-02-29"] {
            check(MobileTaskDates.parse(day).map(MobileTaskDates.string) == day, "Date-only round trip across DST/leap year")
        }
        check(MobileTaskDates.parse(nil) == nil, "Missing date")
        check(MobileTaskDates.parse("") == nil, "Cleared date")
        check(MobileTaskDates.parse("2026-02-30") == nil, "Invalid calendar date")
        check(MobileTaskDates.parse("2026-09-19T23:30:00Z").map(MobileTaskDates.string) == "2026-09-19", "Date-only field is not shifted by timezone")
        print("Passed \(checks) mobile project rules checks.")
    }
}
