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
    var isUploadingImages = false
    var isStreaming = false
    var streamingContent = ""
    var tokenUsage: MWTokenUsage?
    var errorMessage: String?
    var selectedSlideIndex: Int?
    var togglingMode: String?
    private var streamingTask: Task<Void, Never>?

    var currentTaskType: MWTaskType {
        thread?.resolvedTaskType ?? inferMWTaskType(from: currentState)
    }

    var hasPreviewContent: Bool {
        switch currentTaskType {
        case .offerLetter:
            return pdfData != nil
        case .review:
            return currentState["review_title"] != nil
                || currentState["summary"] != nil
                || currentState["strengths"] != nil
        case .workbook:
            return currentState["workbook_title"] != nil
                || (currentState["sections"]?.value as? [AnyCodable])?.isEmpty == false
        case .onboarding:
            return currentState["employees"] != nil || currentState["batch_status"] != nil
        case .presentation:
            return currentState["presentation_title"] != nil || currentState["slides"] != nil
        case .handbook:
            return currentState["handbook_title"] != nil
                || currentState["handbook_sections"] != nil
        case .resumeBatch:
            return currentState["candidates"] != nil
        case .inventory:
            return currentState["inventory_items"] != nil
        case .chat, .policy, .project, .languageTutor, .blog:
            return false
        }
    }

    private let service = MatchaWorkService.shared
    private var streamBasePath: String {
        "\(APIClient.shared.baseURL)/matcha-work"
    }

    private func errorMessage(from data: Data, fallback: String) -> String {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? String {
            return detail
        }
        return String(data: data, encoding: .utf8) ?? fallback
    }

    func loadThread(id: String) async {
        await MainActor.run {
            isLoadingThread = true
            errorMessage = nil
            selectedSlideIndex = nil
            thread = nil
            messages = []
            versions = []
            currentState = [:]
            pdfData = nil
            isLoadingPDF = false
            tokenUsage = nil
        }
        do {
            let detail = try await service.getThread(id: id)
            await MainActor.run {
                thread = detail.thread
                messages = detail.messages
                currentState = detail.currentState
                isLoadingThread = false
            }
            if detail.resolvedTaskType == .offerLetter {
                await loadPDF()
            } else {
                await MainActor.run {
                    pdfData = nil
                }
            }
            await loadVersions()
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoadingThread = false
            }
        }
    }

    func sendMessage(content: String, model: String? = nil) async {
        guard let threadId = thread?.id else { return }
        guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        // Cancel any in-flight stream
        streamingTask?.cancel()

        // Capture and clear slide selection before send
        let capturedSlideIndex = selectedSlideIndex

        // Optimistic local message so the user sees their input immediately.
        // Attach any pending image URLs so screenshots render in the bubble
        // before the server confirms — matches the final persisted metadata.
        let optimisticImages = presentationImageURLs
        let optimisticMeta: MWMessageMetadata? = optimisticImages.isEmpty ? nil : MWMessageMetadata(
            complianceReasoning: nil,
            aiReasoningSteps: nil,
            referencedCategories: nil,
            referencedLocations: nil,
            payerSources: nil,
            affectedEmployees: nil,
            complianceGaps: nil,
            attachments: optimisticImages.map { MWMessageAttachment(url: $0, kind: "image") }
        )
        let tempId = UUID().uuidString
        let localMsg = MWMessage(
            id: tempId,
            threadId: threadId,
            role: "user",
            content: content,
            versionCreated: nil,
            metadata: optimisticMeta,
            createdAt: ISO8601DateFormatter().string(from: Date())
        )

        await MainActor.run {
            messages.append(localMsg)
            isStreaming = true
            streamingContent = ""
            selectedSlideIndex = nil
            errorMessage = nil
            tokenUsage = nil
            // Clear thread-state image chips optimistically since they are now
            // bound to the outgoing user message. The complete event will also
            // return the cleared state from the backend.
            if !optimisticImages.isEmpty {
                currentState["images"] = AnyCodable([String]())
            }
        }

        guard let url = URL(string: "\(streamBasePath)/threads/\(threadId)/messages/stream") else {
            await MainActor.run {
                errorMessage = APIError.invalidURL.localizedDescription
                isStreaming = false
            }
            return
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = APIClient.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        // Explicit idle-byte timeout. Server sends keepalives every 15s during
        // generation, so 90s of silence means something is genuinely wrong
        // (network drop, server crash). Default URLRequest is 60s — too tight
        // to absorb a slow keepalive cycle, too generous to recover quickly.
        request.timeoutInterval = 90

        struct SendBody: Codable {
            let content: String
            let slideIndex: Int?
            let model: String?
            let imageUrls: [String]?
            enum CodingKeys: String, CodingKey {
                case content, model
                case slideIndex = "slide_index"
                case imageUrls = "image_urls"
            }
        }
        // Snapshot any pending image attachments. Backend persists them on the
        // user message metadata and clears them from thread state so the next
        // send starts clean.
        let pendingImages = presentationImageURLs
        request.httpBody = try? JSONEncoder().encode(
            SendBody(
                content: content,
                slideIndex: capturedSlideIndex,
                model: model,
                imageUrls: pendingImages.isEmpty ? nil : pendingImages
            )
        )

        var receivedComplete = false
        let task = Task {
            do {
                let (bytes, response) = try await URLSession.shared.bytes(for: request)
                guard let http = response as? HTTPURLResponse else {
                    throw APIError.noData
                }
                guard (200...299).contains(http.statusCode) else {
                    var errorData = Data()
                    for try await byte in bytes {
                        errorData.append(contentsOf: [byte])
                    }
                    throw APIError.httpError(
                        http.statusCode,
                        errorMessage(from: errorData, fallback: "Streaming failed")
                    )
                }

                for try await line in bytes.lines {
                    try Task.checkCancellation()
                    guard line.hasPrefix("data: ") else { continue }
                    let jsonStr = String(line.dropFirst(6))
                    guard jsonStr != "[DONE]" else { break }
                    guard let data = jsonStr.data(using: .utf8) else { continue }

                    if let event = try? JSONDecoder().decode(SSEEvent.self, from: data) {
                        if event.type == "complete" { receivedComplete = true }
                        await MainActor.run {
                            handleSSEEvent(event, tempMessageId: tempId)
                        }
                    }
                }
            } catch is CancellationError {
                // Task was cancelled — fall through to reload so the user
                // sees the server-saved state on return (cache may be stale).
            } catch let urlError as URLError where urlError.code == .timedOut {
                await MainActor.run {
                    errorMessage = "The AI didn't respond in time. Your message was saved — please try again."
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Streaming failed: \(error.localizedDescription)"
                }
            }

            await MainActor.run {
                isStreaming = false
            }

            // Always invalidate cache so the next view fetches fresh state.
            // The server saves the user message BEFORE generating, so even on
            // total failure the server has it. Without this, a stale 60s-TTL
            // cache hides the message until TTL expires.
            self.service.invalidateThread(threadId: threadId)

            // If stream ended without a complete event, reload now to recover
            // the saved user message + any partial assistant reply. Preserve
            // the original streaming error if reload also fails — the stream
            // error is the actionable one for the user.
            if !receivedComplete {
                let priorError = await MainActor.run { self.errorMessage }
                await reloadThreadData(id: threadId, forceRefresh: true)
                if priorError != nil {
                    await MainActor.run { self.errorMessage = priorError }
                }
            }
        }
        streamingTask = task
        await task.value
    }

    func cancelStreaming() {
        streamingTask?.cancel()
        streamingTask = nil
    }

    @MainActor
    private func handleSSEEvent(_ event: SSEEvent, tempMessageId: String? = nil) {
        switch event.type {
        case "complete":
            guard let data = event.data, let userMessage = data.userMessage else {
                streamingContent = ""
                return
            }

            // Replace optimistic local message with the real server message
            if let tempId = tempMessageId {
                messages.removeAll { $0.id == tempId }
            }
            messages.append(userMessage)
            if let msg = data.assistantMessage {
                messages.append(msg)
            }

            let updatedState = data.currentState ?? currentState
            currentState = updatedState

            if let v = data.version {
                thread?.version = v
            }
            thread?.taskType = data.taskType ?? inferMWTaskType(from: updatedState)

            if let threadId = thread?.id {
                service.invalidateThread(threadId: threadId)
                Task {
                    await loadVersions(forceRefresh: true)
                }
            }

            // Notify any open project panel to refresh — the AI may have written
            // project_sections / posting.content that the panel must re-fetch.
            NotificationCenter.default.post(name: .mwProjectDataChanged, object: nil)

            if let usage = data.resolvedTokenUsage() {
                tokenUsage = usage
            }
            streamingContent = ""

            if currentTaskType == .offerLetter {
                Task { await loadPDF(forceRefresh: true) }
            } else {
                pdfData = nil
            }
        case "usage":
            if let usage = event.data?.resolvedTokenUsage() {
                tokenUsage = usage
            }
        case "error":
            errorMessage = event.message ?? "Unknown streaming error"
        default:
            break
        }
    }

    func loadVersions(forceRefresh: Bool = false) async {
        guard let threadId = thread?.id else { return }
        do {
            let v = try await service.getVersions(threadId: threadId, forceRefresh: forceRefresh)
            await MainActor.run { versions = v }
        } catch { }
    }

    func revert(to version: Int) async {
        guard let threadId = thread?.id else { return }
        do {
            _ = try await service.revertThread(id: threadId, version: version)
            await reloadThreadData(id: threadId, forceRefresh: true)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Reloads thread messages, state, versions, and PDF without showing the loading spinner.
    private func reloadThreadData(id: String, forceRefresh: Bool = false) async {
        do {
            let detail = try await service.getThread(id: id, forceRefresh: forceRefresh)
            await MainActor.run {
                thread = detail.thread
                messages = detail.messages
                currentState = detail.currentState
            }
            if detail.resolvedTaskType == .offerLetter {
                await loadPDF(forceRefresh: forceRefresh)
            } else {
                await MainActor.run {
                    pdfData = nil
                }
            }
            await loadVersions(forceRefresh: forceRefresh)
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
            }
        }
    }

    func finalize() async {
        guard let threadId = thread?.id else { return }
        do {
            _ = try await service.finalizeThread(id: threadId)
            await reloadThreadData(id: threadId, forceRefresh: true)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Mode Toggles

    func toggleMode(_ mode: String) async {
        guard let threadId = thread?.id, togglingMode == nil else { return }
        await MainActor.run { togglingMode = mode }
        do {
            let updated: MWThread
            switch mode {
            case "node":
                updated = try await service.setNodeMode(threadId: threadId, enabled: !(thread?.nodeMode ?? false))
            case "compliance":
                updated = try await service.setComplianceMode(threadId: threadId, enabled: !(thread?.complianceMode ?? false))
            case "payer":
                updated = try await service.setPayerMode(threadId: threadId, enabled: !(thread?.payerMode ?? false))
            default:
                return
            }
            await MainActor.run {
                thread = updated
                togglingMode = nil
            }
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                togglingMode = nil
            }
        }
    }

    // MARK: - Title Update

    func updateTitle(_ newTitle: String) async {
        guard let threadId = thread?.id else { return }
        do {
            let updated = try await service.updateTitle(threadId: threadId, title: newTitle)
            await MainActor.run { thread = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    var presentationImageURLs: [String] {
        guard let raw = currentState["images"] else { return [] }
        if let arr = raw.value as? [AnyCodable] { return arr.compactMap { $0.value as? String } }
        if let arr = raw.value as? [String] { return arr }
        return []
    }

    func uploadImages(_ images: [(data: Data, filename: String, mimeType: String)]) async {
        guard let threadId = thread?.id else { return }
        await MainActor.run { isUploadingImages = true }
        do {
            let urls = try await service.uploadImages(threadId: threadId, images: images)
            await MainActor.run {
                currentState["images"] = AnyCodable(urls.map { AnyCodable($0) })
                isUploadingImages = false
            }
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                isUploadingImages = false
            }
        }
    }

    func removeImage(url: String) async {
        guard let threadId = thread?.id else { return }
        do {
            let urls = try await service.removeImage(threadId: threadId, imageUrl: url)
            await MainActor.run {
                currentState["images"] = AnyCodable(urls.map { AnyCodable($0) })
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func loadPDF(version: Int? = nil) async {
        await loadPDF(version: version, forceRefresh: false)
    }

    func loadPDF(version: Int? = nil, forceRefresh: Bool) async {
        guard let threadId = thread?.id else { return }
        guard currentTaskType == .offerLetter else {
            await MainActor.run {
                pdfData = nil
                isLoadingPDF = false
            }
            return
        }
        await MainActor.run { isLoadingPDF = true }
        do {
            let data = try await service.getPDFData(
                threadId: threadId,
                version: version,
                forceRefresh: forceRefresh
            )
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
// Usage events spread fields directly in data: {"type":"usage","data":{"input_tokens":X,...}}
struct SSEEventData: Codable {
    let userMessage: MWMessage?
    let assistantMessage: MWMessage?
    let currentState: [String: AnyCodable]?
    let version: Int?
    let taskType: MWTaskType?
    let pdfUrl: String?
    let tokenUsage: MWTokenUsage?
    // Flat usage fields (when parent event type == "usage")
    let promptTokens: Int?
    let completionTokens: Int?
    let totalTokens: Int?
    let costDollars: Double?
    let model: String?
    let estimated: Bool?

    enum CodingKeys: String, CodingKey {
        case version, model, estimated
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
        case currentState = "current_state"
        case taskType = "task_type"
        case pdfUrl = "pdf_url"
        case tokenUsage = "token_usage"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case costDollars = "cost_dollars"
    }

    /// Build an MWTokenUsage from flat fields (usage events) or nested token_usage (complete events).
    func resolvedTokenUsage() -> MWTokenUsage? {
        if let tu = tokenUsage { return tu }
        let hasAny = promptTokens != nil || completionTokens != nil || totalTokens != nil || costDollars != nil
        guard hasAny else { return nil }
        return MWTokenUsage(
            promptTokens: promptTokens,
            completionTokens: completionTokens,
            totalTokens: totalTokens,
            costDollars: costDollars,
            model: model,
            estimated: estimated
        )
    }
}

struct SSEEvent: Codable {
    let type: String
    let data: SSEEventData?
    let message: String?  // error events
}
