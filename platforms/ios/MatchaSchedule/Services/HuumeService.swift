import Foundation

/// The schedule assistant: one chat per store and week, turns streamed over
/// server-sent events. Every change it stages waits for a "confirm" turn.
enum HuumeService {
    private struct OpenBody: Encodable {
        let location_id: String
        let week_start: String
        let session_id: String?
    }

    private struct TurnBody: Encodable { let content: String }

    /// A new chat, or the latest one nobody has spoken in yet (the server reuses it).
    static func openSession(location: String, weekStart: Date) async throws -> HuumeSession {
        try await APIClient.shared.request(
            method: "POST", path: "/employee-schedule/assistant/sessions",
            body: OpenBody(location_id: location, week_start: WallClock.format(weekStart, "yyyy-MM-dd"), session_id: nil)
        )
    }

    /// Sends one turn and yields its events until the stream ends. Never
    /// retried after the server answers: a turn is not idempotent.
    static func send(_ content: String, threadID: String) -> AsyncThrowingStream<HuumeEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let bytes = try await open(content, threadID: threadID, refreshOn401: true)
                    for try await line in bytes.lines {
                        guard let event = HuumeSSE.parse(line: line) else { continue }
                        continuation.yield(event)
                        if event == .done { break }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func open(_ content: String, threadID: String, refreshOn401: Bool) async throws -> URLSession.AsyncBytes {
        guard let url = URL(string: APIClient.shared.baseURL + "/matcha-work/threads/\(threadID)/messages/stream") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = APIClient.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder().encode(TurnBody(content: content))
        // Time allowed between bytes, not for the whole turn: the server sends
        // keepalives while a long turn works, so only a stalled stream trips it.
        request.timeoutInterval = 90
        request.cachePolicy = .reloadIgnoringLocalCacheData

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.noData }
        if http.statusCode == 401 && refreshOn401 {
            // Nothing was sent to the model yet: refreshing and sending again is safe.
            bytes.task.cancel()
            _ = try await AuthService.shared.refresh()
            return try await open(content, threadID: threadID, refreshOn401: false)
        }
        guard (200...299).contains(http.statusCode) else {
            var body = Data()
            for try await byte in bytes { body.append(byte); if body.count > 16_384 { break } }
            throw APIError.httpError(http.statusCode, APIClient.shared.extractErrorMessage(from: body) ?? "HTTP \(http.statusCode)")
        }
        return bytes
    }
}
