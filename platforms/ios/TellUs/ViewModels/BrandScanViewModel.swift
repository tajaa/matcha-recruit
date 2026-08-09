import Foundation

/// Counter-side redeem, in the brand owner's own app. Their session is the
/// authentication, so there is no device token in this path.
@MainActor
@Observable
final class BrandScanViewModel {
    enum Outcome: Equatable {
        case success(PromoRedeemResult)
        case alreadyRedeemed(at: String?, store: String?)
        case expired(String)
        case cancelled(String)
        case invalid(String)
    }

    var outcome: Outcome?
    var redeeming = false
    /// Suppresses re-fires while a result is on screen — VisionKit will happily
    /// report the same code many times a second.
    var isScanning = true

    private var lastDecoded: String?

    func handle(decoded: String) async {
        guard !redeeming, outcome == nil else { return }
        // The camera re-reads the same code continuously; without this a single
        // card produces a success followed instantly by an already-redeemed.
        guard decoded != lastDecoded else { return }
        lastDecoded = decoded
        await redeem(cardToken: decoded)
    }

    func redeem(cardToken: String) async {
        guard !redeeming else { return }
        redeeming = true
        isScanning = false
        defer { redeeming = false }
        do {
            outcome = .success(try await PromoService.shared.redeem(cardToken: cardToken))
        } catch {
            if error.isCancellation { isScanning = true; return }
            outcome = Self.outcome(for: error)
        }
    }

    /// Maps the server's structured error body onto something a person at a
    /// counter can act on. The already-redeemed case carries when and where in
    /// `detail.extra` specifically so staff can tell a duplicate from a fraud
    /// attempt — dropping that context is what makes a refusal feel arbitrary.
    static func outcome(for error: Error) -> Outcome {
        guard let api = error as? APIError else {
            return .invalid(error.localizedDescription)
        }
        let detail = api.detail(as: PromoErrorDetail.self)
        switch detail?.code {
        case "already_redeemed":
            return .alreadyRedeemed(at: detail?.redeemed_at, store: detail?.redeemed_store_name)
        case "expired":
            return .expired(detail?.message ?? "This card has expired.")
        case "cancelled", "brand_inactive":
            return .cancelled(detail?.message ?? "This card is no longer valid.")
        default:
            if api.statusCode == 409 { return .alreadyRedeemed(at: nil, store: nil) }
            return .invalid(detail?.message ?? api.localizedDescription)
        }
    }

    func scanNext() {
        outcome = nil
        lastDecoded = nil
        isScanning = true
    }
}
