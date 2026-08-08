import SwiftUI

struct ReportMediaGallery: View {
    let media: [ReportMedia]

    var body: some View {
        if !media.isEmpty {
            ScrollView(.horizontal) {
                HStack {
                    ForEach(media) { item in
                        AsyncMediaImage(media: item).frame(width: 100, height: 100)
                    }
                }
            }
        }
    }
}
