import SwiftUI

/// Optimistic like toggle — the one deliberate exception to this app's
/// apply-the-response convention (ReportDetailViewModel's `run`). A like
/// changes exactly two scalars and the endpoint returns both, so reconciling
/// from the POST/DELETE response is strictly better than a refetch: no full
/// feed reload to move one integer, and the server's authoritative count
/// self-heals any double-tap race.
///
/// Self-contained @State so no ViewModel changes are needed to drop it into
/// a row. Seeds from the row it's rendered for and re-syncs when that row
/// changes underneath it (a feed refetch landing new counts).
struct LikeButton: View {
    let target: LikeTarget
    let id: String
    let initialCount: Int
    let initialLiked: Bool
    var disabled: Bool = false
    var onError: ((String) -> Void)?

    @State private var count: Int
    @State private var liked: Bool
    @State private var inFlight = false

    init(
        target: LikeTarget, id: String, count: Int, liked: Bool,
        disabled: Bool = false, onError: ((String) -> Void)? = nil
    ) {
        self.target = target
        self.id = id
        self.initialCount = count
        self.initialLiked = liked
        self.disabled = disabled
        self.onError = onError
        _count = State(initialValue: count)
        _liked = State(initialValue: liked)
    }

    var body: some View {
        Button {
            Task { await toggle() }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: liked ? "heart.fill" : "heart")
                    .font(.caption)
                if count > 0 {
                    Text("\(count)").font(.caption)
                }
            }
            .foregroundStyle(liked ? TU.ember : TU.textDim)
        }
        .buttonStyle(.plain)
        .disabled(disabled || inFlight)
        // A SwiftUI Button can fire again before the Task resolves; inFlight
        // is the re-entrancy guard (the web LikeButton's `seq` ref equivalent).
        .opacity(disabled ? 0.5 : 1)
        .onChange(of: initialCount) { _, new in if !inFlight { count = new } }
        .onChange(of: initialLiked) { _, new in if !inFlight { liked = new } }
    }

    private func toggle() async {
        guard !inFlight, !disabled else { return }
        inFlight = true
        defer { inFlight = false }

        let prevCount = count
        let prevLiked = liked
        count = prevLiked ? max(0, prevCount - 1) : prevCount + 1
        liked = !prevLiked

        do {
            let state = prevLiked
                ? try await LikesService.shared.unlike(target, id: id)
                : try await LikesService.shared.like(target, id: id)
            count = state.like_count
            liked = state.liked_by_me
        } catch {
            if error.isCancellation { return }
            count = prevCount
            liked = prevLiked
            onError?(error.localizedDescription)
        }
    }
}
