import Foundation

struct FlyerAiSelection: Codable, Equatable {
    let layer: String
    let kind: String?
    let text: String?
}

struct FlyerAiHistoryTurn: Codable, Equatable {
    let role: String
    let content: String
    let ops_summary: String?
}

struct FlyerAssistRequest: Encodable, Equatable {
    let message: String
    let design: FlyerDesign
    let history: [FlyerAiHistoryTurn]
    let selection: FlyerAiSelection?
}

struct FlyerOpResult: Codable, Equatable {
    let ok: Bool
    let summary: String
}

struct FlyerAiRejection: Codable, Equatable {
    let op: JSONValue
    let reason: String
}

struct FlyerAssistResponse: Codable, Equatable {
    let message: String
    let design: FlyerDesign
    let ops: [JSONValue]
    let results: [FlyerOpResult]
    let rejected: [FlyerAiRejection]
}

struct FlyerIdea: Codable, Equatable, Identifiable {
    let key: String
    let label: String
    let blurb: String
    let design: FlyerDesign

    var id: String { key }
}

struct FlyerIdeasResponse: Codable, Equatable {
    let ideas: [FlyerIdea]
}
