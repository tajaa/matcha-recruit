import Foundation

struct DiscoverInviteResponse: Codable {
    let slug: String
    let invite_count: Int
    let already_invited: Bool
    let share_url: String
    let share_text: String
}

final class DiscoverService {
    static let shared = DiscoverService()
    private let client = APIClient.shared
    private init() {}

    func invite(slug: String) async throws -> DiscoverInviteResponse {
        try await client.request(method: "POST", path: "/discover/invite", body: ["slug": slug])
    }

    func discover(
        lat: Double?, lng: Double?, radiusKm: Double = 15,
        q: String?, city: String?, state: String?,
        offset: Int = 0, limit: Int = 12
    ) async throws -> DiscoverPage {
        var items: [URLQueryItem] = []
        if let lat, let lng {
            items.append(URLQueryItem(name: "lat", value: String(lat)))
            items.append(URLQueryItem(name: "lng", value: String(lng)))
            items.append(URLQueryItem(name: "radius_km", value: String(radiusKm)))
        }
        if let q, !q.isEmpty { items.append(URLQueryItem(name: "q", value: q)) }
        if let city, !city.isEmpty { items.append(URLQueryItem(name: "city", value: city)) }
        if let state, !state.isEmpty { items.append(URLQueryItem(name: "state", value: state)) }
        items.append(URLQueryItem(name: "offset", value: String(offset)))
        items.append(URLQueryItem(name: "limit", value: String(limit)))
        let qs = PlacesService.queryString(items)
        return try await client.request(method: "GET", path: "/discover" + qs)
    }
}
