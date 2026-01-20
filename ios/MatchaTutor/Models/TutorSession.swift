import Foundation

enum TutorMode: String, Codable, CaseIterable {
    case interviewPrep = "interview_prep"
    case languageTest = "language_test"

    var displayName: String {
        switch self {
        case .interviewPrep: return "Interview Prep"
        case .languageTest: return "Language Test"
        }
    }
}

enum TutorLanguage: String, Codable, CaseIterable {
    case english = "en"
    case spanish = "es"

    var displayName: String {
        switch self {
        case .english: return "English"
        case .spanish: return "Spanish"
        }
    }
}

enum InterviewRole: String, Codable, CaseIterable {
    case vpOfPeople = "VP of People"
    case cto = "CTO"
    case headOfMarketing = "Head of Marketing"
    case juniorEngineer = "Junior Engineer"

    var displayName: String { rawValue }

    var description: String {
        switch self {
        case .vpOfPeople: return "HR leadership"
        case .cto: return "Technical leadership"
        case .headOfMarketing: return "Marketing leadership"
        case .juniorEngineer: return "Entry-level technical role"
        }
    }
}

struct TutorSessionCreateRequest: Codable {
    let mode: TutorMode
    let language: TutorLanguage?
    let durationMinutes: Int?
    let interviewRole: String?

    enum CodingKeys: String, CodingKey {
        case mode, language
        case durationMinutes = "duration_minutes"
        case interviewRole = "interview_role"
    }
}

struct TutorSessionResponse: Codable {
    let interviewId: String
    let websocketUrl: String
    let maxSessionDurationSeconds: Int

    enum CodingKeys: String, CodingKey {
        case interviewId = "interview_id"
        case websocketUrl = "websocket_url"
        case maxSessionDurationSeconds = "max_session_duration_seconds"
    }
}

struct TutorSessionSummary: Codable, Identifiable {
    let id: String
    let interviewType: String
    let language: String?
    let status: String
    let overallScore: Double?
    let createdAt: String
    let completedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case interviewType = "interview_type"
        case language, status
        case overallScore = "overall_score"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }
}

// Session duration options
enum SessionDuration: Int, CaseIterable {
    case short = 2
    case medium = 5
    case long = 8

    var displayName: String {
        "\(rawValue) min"
    }
}
