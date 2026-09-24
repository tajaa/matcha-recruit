import Foundation

struct ScheduleSnapshot {
    let mine: [ScheduleShift]
    let team: [ScheduleShift]
    let open: [ScheduleShift]
    let locations: [String: String]
}

enum ScheduleService {
    static func load(week: Date) async throws -> ScheduleSnapshot {
        let (start, end) = WallClock.range(starting: week)
        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end)
        ]
        let query = components.percentEncodedQuery ?? ""
        async let mine: ShiftListResponse = APIClient.shared.request(method: "GET", path: "/v1/portal/me/schedule?\(query)")
        async let team: ShiftListResponse = APIClient.shared.request(method: "GET", path: "/v1/portal/me/schedule?\(query)&team=true")
        async let open: ShiftListResponse = APIClient.shared.request(method: "GET", path: "/v1/portal/me/schedule/open-seats?\(query)")
        async let places: LocationsResponse = APIClient.shared.request(method: "GET", path: "/locations")
        let (myResult, teamResult, openResult, placeResult) = try await (mine, team, open, places)
        return ScheduleSnapshot(
            mine: myResult.shifts, team: teamResult.shifts, open: openResult.shifts,
            locations: Dictionary(uniqueKeysWithValues: placeResult.locations.map { ($0.id, $0.name) })
        )
    }
}
