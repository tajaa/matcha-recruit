import SwiftUI

/// Displays report/review media whose `url` is a 15-minute presigned GET.
/// Bytes are loaded via MediaByteLoader (cached by media id, never by URL);
/// on failure `onFailure` lets the caller refetch its parent detail once to
/// re-mint a fresh presigned URL — this view itself just shows a
/// broken-image fallback.
struct AsyncMediaImage: View {
    let media: ReportMedia
    var onFailure: (() -> Void)? = nil
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else if failed {
                Image(systemName: media.media_type == .video ? "video.slash" : "photo.badge.exclamationmark")
                    .foregroundStyle(.secondary)
            } else {
                ProgressView()
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        // Keyed on the presigned URL (not just media.id) so a parent refetch
        // that re-mints a fresh URL for the same media id naturally retries.
        .task(id: media.url ?? media.id) {
            image = nil
            failed = false
            do {
                let data = try await MediaByteLoader.shared.data(for: media)
                let decoded = await Task.detached(priority: .userInitiated) { UIImage(data: data) }.value
                if let decoded {
                    image = decoded
                } else {
                    failed = true
                    onFailure?()
                }
            } catch {
                failed = true
                onFailure?()
            }
        }
    }
}
