import Foundation

enum MobileProjectFilter: String, CaseIterable, Identifiable {
    case all = "All", solo = "Solo", collab = "Together", archived = "Archived"
    var id: String { rawValue }
}

enum MobileProjectRules {
    static func visibleProjects(_ projects: [MWProject], filter: MobileProjectFilter, query: String) -> [MWProject] {
        let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return projects.filter { project in
            guard project.projectType == nil || ["general", "collab"].contains(project.projectType ?? "") else { return false }
            guard (project.status == "archived") == (filter == .archived) else { return false }
            if filter == .solo && project.projectType == "collab" { return false }
            if filter == .collab && project.projectType != "collab" { return false }
            return search.isEmpty || project.title.localizedStandardContains(search)
        }.sorted {
            if ($0.isPinned == true) != ($1.isPinned == true) { return $0.isPinned == true }
            if $0.updatedAt != $1.updatedAt { return ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            return $0.id < $1.id
        }
    }
}

extension MWProject {
    // Mirrors _can_edit_project. The server remains the authority for every
    // write; nil is the legacy owner/company-access role.
    var mobileCanEdit: Bool { !["viewer", "commenter"].contains(collaboratorRole ?? "") }
    var mobileIsOwner: Bool { collaboratorRole == nil || collaboratorRole == "owner" }
}

enum MobileTaskDates {
    static func formatter() -> DateFormatter {
        let value = DateFormatter()
        value.locale = Locale(identifier: "en_US_POSIX")
        value.calendar = Calendar(identifier: .gregorian)
        value.dateFormat = "yyyy-MM-dd"
        value.isLenient = false
        return value
    }
    static func parse(_ value: String?) -> Date? { value.flatMap { formatter().date(from: String($0.prefix(10))) } }
    static func string(_ value: Date) -> String { formatter().string(from: value) }
}
