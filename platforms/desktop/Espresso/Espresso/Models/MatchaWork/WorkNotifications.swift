import Foundation

extension Notification.Name {
    static let mwCreateNewThread = Notification.Name("mwCreateNewThread")
    static let mwThreadsChanged = Notification.Name("mwThreadsChanged")
    static let mwProjectDataChanged = Notification.Name("mwProjectDataChanged")
    static let mwProjectTitlePatched = Notification.Name("mwProjectTitlePatched")
    static let mwCollabFilesBrowse = Notification.Name("mwCollabFilesBrowse")
}

struct MWProjectTitlePatch {
    let id: String
    let title: String
}
