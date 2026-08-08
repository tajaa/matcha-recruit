import SwiftUI

struct ReportMediaGallery: View {
    let media: [ReportMedia]
    var onFailure: (() -> Void)? = nil

    var body: some View {
        if !media.isEmpty {
            ScrollView(.horizontal) {
                HStack {
                    ForEach(media) { item in
                        if item.media_type == .video {
                            MediaVideoView(media: item, onFailure: onFailure).frame(width: 100, height: 100)
                        } else {
                            AsyncMediaImage(media: item, onFailure: onFailure).frame(width: 100, height: 100)
                        }
                    }
                }
            }
        }
    }
}
