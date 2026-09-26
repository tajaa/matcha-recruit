import Foundation

struct ScheduleSnapshot {
    let mine: [ScheduleShift]
    let team: [ScheduleShift]
    let open: [ScheduleShift]
    let locations: [String: String]
    /// The employee's store week start (0 = Sunday); Sunday when unknown.
    let weekStartWeekday: Int
}

enum ScheduleService {
    static func teamShifts(from start: Date, through end: Date) async throws -> [ScheduleShift] {
        let from = WallClock.range(starting: start).0
        let until = WallClock.range(starting: end).0
        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "start", value: from),
            URLQueryItem(name: "end", value: until),
            URLQueryItem(name: "team", value: "true")
        ]
        let response: ShiftListResponse = try await APIClient.shared.request(
            method: "GET", path: "/v1/portal/me/schedule?\(components.percentEncodedQuery ?? "")"
        )
        return response.shifts
    }

    /// `team=true` is company-wide, but `/locations` only returns the
    /// employee's own store: keep the Team tab to shifts at that store (or
    /// locationless ones) so a multi-store company does not mix stores with
    /// no way to tell them apart. No known store ⇒ nothing to filter by.
    static func storeScoped(_ shifts: [ScheduleShift], locationIDs: Set<String>) -> [ScheduleShift] {
        guard !locationIDs.isEmpty else { return shifts }
        return shifts.filter { $0.location_id == nil || locationIDs.contains($0.location_id!) }
    }

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
        let locationIDs = Set(placeResult.locations.map(\.id))
        return ScheduleSnapshot(
            mine: myResult.shifts,
            team: storeScoped(teamResult.shifts, locationIDs: locationIDs),
            open: openResult.shifts,
            locations: Dictionary(uniqueKeysWithValues: placeResult.locations.map { ($0.id, $0.name) }),
            weekStartWeekday: placeResult.locations.first?.week_start_weekday ?? 0
        )
    }
}
