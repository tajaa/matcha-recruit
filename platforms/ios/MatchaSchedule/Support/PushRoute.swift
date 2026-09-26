import Foundation

enum PushDestination: Equatable {
    case schedule
    case requests
    case inbox(String)
}

enum PushRoute {
    static func destination(for payload: [AnyHashable: Any]) -> PushDestination? {
        let type = payload["type"] as? String ?? ""
        let metadata = payload["metadata"] as? [String: Any] ?? [:]
        if type == "inbox_message" {
            let id = metadata["conversation_id"] as? String ?? payload["conversation_id"] as? String
            if let id, UUID(uuidString: id) != nil { return .inbox(id) }
        }
        if type == "schedule_published" { return .schedule }
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
        default: return nil
        }
    }
}
