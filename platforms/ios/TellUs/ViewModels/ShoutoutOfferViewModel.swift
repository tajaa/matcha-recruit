import Foundation

@MainActor
@Observable
final class ShoutoutOfferViewModel {
    enum Phase: Equatable {
        case loading
        case preview(ShoutoutOfferPreview)
        case claimed(PromoCard)
        case unavailable
        case failed(String)
    }

    var phase: Phase = .loading
    var claiming = false
    var error: String?

    private let token: String?
    private let code: String?

    init(token: String? = nil, code: String? = nil) {
        self.token = token
        self.code = code
    }

    func load() async {
        phase = .loading
        do {
            let preview = try await PromoService.shared.shoutoutPreview(token: token, code: code)
            if preview.already_claimed, let cardToken = preview.card_token {
                phase = .claimed(try await PromoService.shared.card(token: cardToken))
            } else if preview.available {
                phase = .preview(preview)
            } else {
                phase = .unavailable
            }
        } catch {
            if error.isCancellation { return }
            phase = .failed(error.localizedDescription)
        }
    }

    func claim() async {
        guard !claiming else { return }
        claiming = true
        defer { claiming = false }
        do {
            let result = try await PromoService.shared.claimShoutout(token: token, code: code)
            phase = .claimed(try await PromoService.shared.card(token: result.card_token))
        } catch {
            if error.isCancellation { return }
            if let api = error as? APIError, api.statusCode == 410 {
                await load()
            } else {
                self.error = error.localizedDescription
            }
        }
    }
}
