import Foundation

/// Report/review media URLs are presigned GETs with a 15-minute TTL, minted
/// fresh on every response. Cache the downloaded BYTES keyed by media id —
/// NEVER the URL — and fetch with `.reloadIgnoringLocalCacheData` so a
/// presigned URL never lands in URLCache's disk store.
final class MediaByteLoader {
    static let shared = MediaByteLoader()
    private let cache = LockedCache<Data>()
    private let ttl: TimeInterval = 30 * 60
    private init() {}

    enum LoaderError: Error { case noURL }

    func data(for media: ReportMedia) async throws -> Data {
        if let cached = cache[media.id], cached.isValid {
            return cached.value
        }
        guard let urlString = media.url, let url = URL(string: urlString) else {
            throw LoaderError.noURL
        }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, "Media fetch failed")
        }
        cache[media.id] = CacheEntry(value: data, expiresAt: Date().addingTimeInterval(ttl))
        return data
    }
}
