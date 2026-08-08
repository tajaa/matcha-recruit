import Foundation

final class PlacesService {
    static let shared = PlacesService()
    private let client = APIClient.shared
    private init() {}

    func search(q: String) async throws -> [PlaceSearchResult] {
        var components = URLComponents()
        components.queryItems = [URLQueryItem(name: "q", value: q)]
        let qs = components.percentEncodedQuery.map { "?" + $0 } ?? ""
        return try await client.request(method: "GET", path: "/places/search" + qs)
    }

    func autocomplete(q: String, sessionToken: String) async throws -> [PlaceSuggestion] {
        var components = URLComponents()
        components.queryItems = [
            URLQueryItem(name: "q", value: q),
            URLQueryItem(name: "st", value: sessionToken),
        ]
        let qs = components.percentEncodedQuery.map { "?" + $0 } ?? ""
        return try await client.request(method: "GET", path: "/places/autocomplete" + qs)
    }

    func create(_ body: PlaceCreateRequest) async throws -> PlaceCreateResponse {
        try await client.request(method: "POST", path: "/places", body: body)
    }
}
