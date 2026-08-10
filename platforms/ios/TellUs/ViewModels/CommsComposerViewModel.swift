import Foundation
import Observation

@MainActor
@Observable
final class CommsComposerViewModel: LoadableVM {
    let slug: String
    var page: PublicBrandPage?
    var selectedStoreID: String?
    var topic: DmTopic = .other
    var body = ""
    var isLoading = false
    var isSending = false
    var error: String?
    var startedThread: DmThread?

    private var clientMessageID: String?

    init(slug: String) { self.slug = slug }

    var stores: [MessagingStore] { page?.stores ?? [] }
    var needsStoreSelection: Bool { stores.count > 1 }
    var canSend: Bool {
        guard let page, page.claimed, page.messaging_enabled else { return false }
        if needsStoreSelection && selectedStoreID == nil { return false }
        return !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func load() async {
        await withLoad {
            let fetched = try await PublicBrandService.shared.brand(slug: slug)
            page = fetched
            if fetched.stores.count == 1 { selectedStoreID = fetched.stores[0].id }
        }
    }

    func setBody(_ value: String) {
        body = value
        clientMessageID = nil
    }

    func send() async {
        guard canSend else {
            error = needsStoreSelection && selectedStoreID == nil
                ? "Choose a location first."
                : "Write a question first."
            return
        }
        guard let page else { return }
        isSending = true
        error = nil
        let id = clientMessageID ?? UUID().uuidString
        clientMessageID = id
        defer { isSending = false }
        do {
            let result = try await DmService.shared.start(
                slug: page.slug,
                request: CommsStartRequest(
                    storeID: selectedStoreID,
                    topic: topic,
                    body: body.trimmingCharacters(in: .whitespacesAndNewlines),
                    clientMessageId: id
                )
            )
            startedThread = result.thread
            clientMessageID = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
