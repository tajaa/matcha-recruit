import SwiftUI

/// Displays report/review media whose `url` is a 15-minute presigned GET.
/// Bytes are loaded via MediaByteLoader (cached by media id, never by URL);
/// on failure the caller's parent list should be refetched to re-mint a
/// fresh URL — this view itself just shows a broken-image fallback.
struct AsyncMediaImage: View {
    let media: ReportMedia
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
        .task {
            do {
                let data = try await MediaByteLoader.shared.data(for: media)
                image = UIImage(data: data)
            } catch {
                failed = true
            }
        }
    }
}
