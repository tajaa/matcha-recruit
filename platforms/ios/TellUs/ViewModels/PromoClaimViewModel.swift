import Foundation

@MainActor
@Observable
final class PromoClaimViewModel: LoadableVM {
    enum Phase: Equatable {
        case loading
        case preview(PromoClaimPreview)
        case claimed(PromoCard)
        case unavailable(reason: String, message: String)
        case failed(String)
    }

    var isLoading = false
    var error: String?
    var phase: Phase = .loading
    var claiming = false

    private let token: String

    init(token: String) {
        self.token = token
    }

    /// Copy for every `ClaimUnavailableReason` the server can return. Mirrors
    /// `_CLAIM_UNAVAILABLE_MESSAGES` — a reason with no entry here would show a
    /// blank panel, so the default says something true rather than nothing.
    static func message(for reason: String) -> String {
        switch reason {
        case "cap_reached": return "Every reward from this offer has been claimed."
        case "cancelled": return "This offer was cancelled."
        case "paused": return "This offer is paused right now — check back later."
        case "not_started": return "This offer hasn't started yet."
        case "ended": return "This offer has ended."
        case "brand_inactive": return "This brand's account is no longer active."
        case "location_required": return "Sign in and enable location to claim this local offer."
        case "outside_radius": return "This offer is only available while you are near the store."
        case "not_pushed": return "This local offer has not been sent yet."
        default: return "This offer isn't available right now."
        }
    }

    func load() async {
        phase = .loading
        do {
            let preview = try await PromoService.shared.claimPreview(token: token)
            if preview.already_claimed, let cardToken = preview.card_token {
                // Already holds one — go straight to it. The claim endpoint is
                // idempotent, but showing the card beats making them tap again.
                phase = .claimed(try await PromoService.shared.card(token: cardToken))
            } else if preview.available {
                phase = .preview(preview)
            } else {
                phase = .unavailable(reason: preview.reason, message: Self.message(for: preview.reason))
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
            phase = .claimed(try await PromoService.shared.claim(token: token).card)
        } catch {
            if error.isCancellation { return }
            // A 410 means the window closed between preview and tap — re-read
            // so the reason panel explains which way it closed.
            if let api = error as? APIError, api.statusCode == 410 {
                await load()
                return
            }
            self.error = error.localizedDescription
        }
    }
}
