import Foundation

/// A scheduling write the server refused with a 409 a manager may override
/// (`?force=true` / `force: true`): a double-booking, a full shift, time
/// outside someone's availability, an unqualified person, or an advisory
/// scheduling-law flag. A hard limit (`schedule_compliance_block`, 422) is
/// never one of these: it stays an ordinary error.
struct ScheduleConflict: Equatable {
    static let forceableCodes: Set<String> = [
        "schedule_conflict", "shift_full", "outside_availability",
        "not_qualified_for_job", "schedule_compliance",
    ]

    struct Violation: Equatable {
        let check: String?
        let message: String
        let statute: String?
    }

    struct Overlap: Equatable {
        let starts_at: String
        let ends_at: String
        let role: String?
    }

    let code: String
    let message: String
    let violations: [Violation]
    let overlaps: [Overlap]

    /// A meal-break advisory needs a break plan on the shift, not a
    /// force-through (the web editor's rule, `scheduleConflicts.ts`).
    var isMealBreak: Bool {
        code == "schedule_compliance" && violations.contains { $0.check == "meal_break" }
    }

    /// What the "Schedule anyway?" prompt says, in the web's words.
    var prompt: String {
        switch code {
        case "schedule_conflict":
            let lines = overlaps.map { overlap -> String in
                let day = WallClock.label(overlap.starts_at, format: "EEE, MMM d")
                let from = WallClock.label(overlap.starts_at, format: "h:mm a")
                let to = WallClock.label(overlap.ends_at, format: "h:mm a")
                let role = overlap.role.map { " (\($0))" } ?? ""
                return "• \(day) \(from)–\(to)\(role)"
            }
            return (["Already scheduled during this time:"] + lines).joined(separator: "\n")
        case "schedule_compliance":
            let lines = violations.map { "• \($0.message)" + ($0.statute.map { " [\($0)]" } ?? "") }
            let allFairWorkweek = !violations.isEmpty
                && violations.allSatisfy { $0.check?.hasPrefix("fair_workweek_") == true }
            let lead = allFairWorkweek
                ? "This change may trigger Fair Workweek obligations:"
                : "This shift may not comply with scheduling law:"
            return ([lead] + lines).joined(separator: "\n")
        case "outside_availability":
            return (["Outside this employee's logged availability:"] + violations.map { "• \($0.message)" })
                .joined(separator: "\n")
        default:
            return message
        }
    }

    /// The forceable conflict in a FastAPI error body, or nil.
    static func parse(status: Int, data: Data) -> ScheduleConflict? {
        guard status == 409,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = json["detail"] as? [String: Any],
              let code = detail["code"] as? String,
              forceableCodes.contains(code) else { return nil }
        let violations = (detail["violations"] as? [[String: Any]] ?? []).compactMap { item -> Violation? in
            guard let message = item["message"] as? String else { return nil }
            return Violation(check: item["check"] as? String, message: message, statute: item["statute"] as? String)
        }
        let overlaps = (detail["conflicts"] as? [[String: Any]] ?? []).compactMap { item -> Overlap? in
            guard let starts = item["starts_at"] as? String, let ends = item["ends_at"] as? String else { return nil }
            return Overlap(starts_at: starts, ends_at: ends, role: item["role"] as? String)
        }
        return ScheduleConflict(
            code: code,
            message: detail["message"] as? String ?? "This change needs your confirmation.",
            violations: violations,
            overlaps: overlaps
        )
    }
}
