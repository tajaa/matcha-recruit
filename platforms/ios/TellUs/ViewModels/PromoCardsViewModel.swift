import Foundation

@MainActor
@Observable
final class PromoCardsViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var cards: [PromoCard] = []

    func load() async {
        await withLoad {
            cards = try await PromoService.shared.myCards()
        }
    }

    /// Cards worth acting on float to the top; spent and dead ones keep their
    /// place below rather than disappearing, since "did I already use that?" is
    /// the question the wallet exists to answer.
    var grouped: (active: [PromoCard], past: [PromoCard]) {
        (cards.filter { $0.isRedeemable }, cards.filter { !$0.isRedeemable })
    }
}
