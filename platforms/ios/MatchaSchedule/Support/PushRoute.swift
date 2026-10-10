import Foundation

enum PushDestination: Equatable {
    case schedule
    case requests
    case inbox(String)
    /// A request waiting for a manager; the id opens it when known.
    case manageApprovals(String?)
}

enum PushRoute {
    static func destination(for payload: [AnyHashable: Any]) -> PushDestination? {
        let type = payload["type"] as? String ?? ""
        let metadata = payload["metadata"] as? [String: Any] ?? [:]
        if type == "inbox_message" {
            let id = metadata["conversation_id"] as? String ?? payload["conversation_id"] as? String
            if let id, UUID(uuidString: id) != nil { return .inbox(id) }
        }
        if type == "schedule_published" || type == "schedule_break_reminder" { return .schedule }
        // Before the generic rule: this one is for the manager, not the requester.
        if type == "schedule_request_pending" {
            let id = metadata["request_id"] as? String
            return .manageApprovals(id.flatMap { UUID(uuidString: $0) == nil ? nil : $0 })
        }
        if type.hasPrefix("schedule_") { return .requests }
        let link = payload["link"] as? String ?? metadata["link"] as? String
        return link.flatMap(URL.init(string:)).flatMap(destination(for:))
    }

    static func destination(for url: URL) -> PushDestination? {
        guard url.scheme == "matchaschedule" else { return nil }
        switch url.host {
        case "schedule": return .schedule
        case "requests": return .requests
        case "inbox":
            guard let id = url.pathComponents.dropFirst().first, UUID(uuidString: id) != nil else { return nil }
            return .inbox(id)
        case "manage":
            // matchaschedule://manage or matchaschedule://manage/requests/{id}
            let parts = Array(url.pathComponents.dropFirst())
            if parts.count == 2, parts[0] == "requests", UUID(uuidString: parts[1]) != nil {
                return .manageApprovals(parts[1])
            }
            return .manageApprovals(nil)
        default: return nil
        }
    }
}
