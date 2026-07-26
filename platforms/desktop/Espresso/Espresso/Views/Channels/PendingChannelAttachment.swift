import Foundation

struct PendingChannelAttachment: Identifiable, Hashable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String
    var size: Int { data.count }
    var isImage: Bool { mimeType.hasPrefix("image/") }
}
