import AVKit
import SwiftUI

/// Video counterpart of AsyncMediaImage. The old approach downloaded the
/// whole video via MediaByteLoader and tried `UIImage(data:)` on it (always
/// nil for a video, so `failed` never set — infinite spinner). This instead
/// streams the presigned URL directly through AVPlayer; nothing is
/// downloaded ahead of time.
struct MediaVideoView: View {
    let media: ReportMedia
    var onFailure: (() -> Void)? = nil
    @State private var showPlayer = false
    @State private var invalidURL = false

    private var playURL: URL? {
        guard let urlString = media.url else { return nil }
        return URL(string: urlString)
    }

    var body: some View {
        Group {
            if invalidURL {
                Image(systemName: "video.slash")
                    .foregroundStyle(.secondary)
            } else {
                Button {
                    if playURL != nil { showPlayer = true }
                } label: {
                    ZStack {
                        Color.black.opacity(0.85)
                        Image(systemName: "play.circle.fill")
                            .font(.interTitle)
                            .foregroundStyle(.white)
                    }
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .onAppear {
            if playURL == nil {
                invalidURL = true
                onFailure?()
            }
        }
        .fullScreenCover(isPresented: $showPlayer) {
            if let playURL {
                VideoPlayer(player: AVPlayer(url: playURL))
                    .ignoresSafeArea()
            }
        }
    }
}
