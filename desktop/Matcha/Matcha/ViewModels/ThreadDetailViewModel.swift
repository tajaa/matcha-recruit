import Foundation

@Observable
class ThreadDetailViewModel {
    var thread: MWThread?
    var messages: [MWMessage] = []
    var versions: [MWDocumentVersion] = []
    var currentState: [String: AnyCodable] = [:]
    var pdfData: Data?
    var isLoadingThread = false
    var isLoadingPDF = false
    var isStreaming = false
    var streamingContent = ""
    var tokenUsage: MWTokenUsage?
    var errorMessage: String?

    private let service = MatchaWorkService.shared
    private let basePath = "http://127.0.0.1:8001/api/matcha-work"

    func loadThread(id: String) async {
        await MainActor.run {
            isLoadingThread = true
            errorMessage = nil
        }
        do {
            let detail = try await service.getThread(id: id)
            await MainActor.run {
                thread = detail.thread
                messages = detail.messages
                currentState = detail.currentState ?? [:]
                isLoadingThread = false
            }
            // Load PDF if offer letter
            if detail.thread.taskType == "offer_letter" {
                await loadPDF()
            }
            await loadVersions()
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoadingThread = false
            }
        }
    }

    func sendMessage(content: String) async {
        guard let threadId = thread?.id else { return }
        guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        // Optimistically add user message
        let tempUserMsg = MWMessage(
            id: UUID().uuidString,
            threadId: threadId,
            role: "user",
            content: content,
            versionCreated: nil,
            createdAt: ISO8601DateFormatter().string(from: Date())
        )
        await MainActor.run {
            messages.append(tempUserMsg)
            isStreaming = true
            streamingContent = ""
        }

        guard let url = URL(string: "\(basePath)/threads/\(threadId)/messages/stream") else {
            await MainActor.run { isStreaming = false }
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = KeychainHelper.load(key: KeychainHelper.Keys.accessToken) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        struct SendBody: Codable {
            let content: String
        }
        request.httpBody = try? JSONEncoder().encode(SendBody(content: content))

        do {
            let (bytes, _) = try await URLSession.shared.bytes(for: request)
            for try await line in bytes.lines {
                guard line.hasPrefix("data: ") else { continue }
                let jsonStr = String(line.dropFirst(6))
                guard jsonStr != "[DONE]" else { break }
                guard let data = jsonStr.data(using: .utf8) else { continue }

                if let event = try? JSONDecoder().decode(SSEEvent.self, from: data) {
                    await MainActor.run {
                        handleSSEEvent(event)
                    }
                }
            }
        } catch {
            await MainActor.run {
                errorMessage = "Streaming failed: \(error.localizedDescription)"
            }
        }

        await MainActor.run {
            isStreaming = false
        }
    }

    @MainActor
    private func handleSSEEvent(_ event: SSEEvent) {
        switch event.type {
        case "complete":
            if let msg = event.data?.assistantMessage {
                messages.append(msg)
            }
            if let v = event.data?.version {
                thread?.version = v
            }
            if let state = event.data?.currentState {
                currentState = state
            }
            streamingContent = ""
            if thread?.taskType == "offer_letter" {
                Task { await loadPDF() }
            }
        case "error":
            errorMessage = event.message ?? "Unknown streaming error"
        default:
            break
        }
    }

    func loadVersions() async {
        guard let threadId = thread?.id else { return }
        do {
            let v = try await service.getVersions(threadId: threadId)
            await MainActor.run { versions = v }
        } catch { }
    }

    func revert(to version: Int) async {
        guard let threadId = thread?.id else { return }
        do {
            let updated = try await service.revertThread(id: threadId, version: version)
            await MainActor.run { thread = updated }
            await loadThread(id: threadId)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func finalize() async {
        guard let threadId = thread?.id else { return }
        do {
            let updated = try await service.finalizeThread(id: threadId)
            await MainActor.run { thread = updated }
            await loadPDF()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func loadPDF(version: Int? = nil) async {
        guard let threadId = thread?.id else { return }
        await MainActor.run { isLoadingPDF = true }
        do {
            let data = try await service.getPDFData(threadId: threadId, version: version)
            await MainActor.run {
                pdfData = data
                isLoadingPDF = false
            }
        } catch {
            await MainActor.run { isLoadingPDF = false }
        }
    }
}

// SSE event structs — backend sends {"type":"complete","data":{...}} or {"type":"error","message":"..."}
struct SSEEventData: Codable {
    let userMessage: MWMessage?
    let assistantMessage: MWMessage?
    let currentState: [String: AnyCodable]?
    let version: Int?
    let pdfUrl: String?

    enum CodingKeys: String, CodingKey {
        case version
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
        case currentState = "current_state"
        case pdfUrl = "pdf_url"
    }
}

struct SSEEvent: Codable {
    let type: String
    let data: SSEEventData?
    let message: String?  // error events
}
