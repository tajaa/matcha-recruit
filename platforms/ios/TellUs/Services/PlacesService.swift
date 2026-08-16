import Foundation

final class PlacesService {
    static let shared = PlacesService()
    private let client = APIClient.shared
    private init() {}

    func search(q: String) async throws -> [PlaceSearchResult] {
        let qs = queryString([URLQueryItem(name: "q", value: q)])
        return try await client.request(method: "GET", path: "/places/search" + qs)
    }

    func autocomplete(q: String, sessionToken: String) async throws -> [PlaceSuggestion] {
        let qs = queryString([
            URLQueryItem(name: "q", value: q),
            URLQueryItem(name: "st", value: sessionToken),
        ])
        return try await client.request(method: "GET", path: "/places/autocomplete" + qs)
    }

    func create(_ body: PlaceCreateRequest) async throws -> PlaceCreateResponse {
        try await client.request(method: "POST", path: "/places", body: body)
    }

    func follow(slug: String) async throws -> FollowedBrand {
        try await client.request(method: "POST", path: "/places/\(slug)/follow")
    }

    func unfollow(slug: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/places/\(slug)/follow")
    }

    /// `percentEncodedQuery` leaves "+" literal (valid per RFC 3986), but the
    /// server's Starlette `parse_qsl` decodes "+" as a space — force-encode it.
    static func queryString(_ items: [URLQueryItem]) -> String {
        var components = URLComponents()
        components.queryItems = items
        return components.percentEncodedQuery
            .map { "?" + $0.replacingOccurrences(of: "+", with: "%2B") }
            ?? ""
    }

    private func queryString(_ items: [URLQueryItem]) -> String {
        Self.queryString(items)
    }
}
