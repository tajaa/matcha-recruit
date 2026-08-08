import Foundation

/// Report/review media URLs are presigned GETs with a 15-minute TTL, minted
/// fresh on every response. Cache the downloaded BYTES keyed by media id —
/// NEVER the URL — and fetch with `.reloadIgnoringLocalCacheData` so a
/// presigned URL never lands in URLCache's disk store.
///
/// Byte-budget LRU: unbounded growth here means every video/photo a user has
/// ever viewed this session stays resident. Evicts least-recently-accessed
/// entries once the total exceeds `maxTotalBytes`; items larger than
/// `maxItemBytes` are returned but never cached (a single huge video
/// shouldn't evict everything else).
final class MediaByteLoader {
    static let shared = MediaByteLoader()

    private struct Entry {
        let data: Data
        let expiresAt: Date
        var lastAccess: Date
    }

    private let lock = NSLock()
    private var entries: [String: Entry] = [:]
    private var totalBytes = 0
    private let ttl: TimeInterval = 30 * 60
    private let maxTotalBytes = 50_000_000
    private let maxItemBytes = 8_000_000
    private init() {}

    enum LoaderError: Error { case noURL }

    func data(for media: ReportMedia) async throws -> Data {
        if let cached = read(media.id) {
            return cached
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
        store(media.id, data: data)
        return data
    }

    /// Clears all cached bytes — called on logout so a shared device never
    /// shows the previous account's media.
    func reset() {
        lock.lock(); defer { lock.unlock() }
        entries.removeAll()
        totalBytes = 0
    }

    private func read(_ id: String) -> Data? {
        lock.lock(); defer { lock.unlock() }
        guard var entry = entries[id] else { return nil }
        guard entry.expiresAt > Date() else {
            entries.removeValue(forKey: id)
            totalBytes -= entry.data.count
            return nil
        }
        entry.lastAccess = Date()
        entries[id] = entry
        return entry.data
    }

    private func store(_ id: String, data: Data) {
        guard data.count <= maxItemBytes else { return }
        lock.lock(); defer { lock.unlock() }
        entries[id] = Entry(data: data, expiresAt: Date().addingTimeInterval(ttl), lastAccess: Date())
        totalBytes += data.count
        while totalBytes > maxTotalBytes, let oldestKey = entries.min(by: { $0.value.lastAccess < $1.value.lastAccess })?.key {
            totalBytes -= entries[oldestKey]?.data.count ?? 0
            entries.removeValue(forKey: oldestKey)
        }
    }
}
