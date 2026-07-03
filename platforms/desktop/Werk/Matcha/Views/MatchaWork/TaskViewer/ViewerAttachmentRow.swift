import SwiftUI

/// One task-level file row in the ATTACHMENTS section: uploader avatar +
/// thumbnail (images) or doc icon + filename + size. Tap to preview.
struct ViewerAttachmentRow: View {
    let file: MWProjectFile
    let onTap: () -> Void
    @State private var isHovered = false

    private var sizeLabel: String {
        let bytes = Double(file.fileSize)
        if bytes < 1024 { return "\(file.fileSize) B" }
        if bytes < 1024 * 1024 { return String(format: "%.1f KB", bytes / 1024) }
        return String(format: "%.1f MB", bytes / 1024 / 1024)
    }

    var body: some View {
        HStack(spacing: 8) {
            // Uploader pfp so "who attached this" is visible at a glance —
            // matches the per-event avatar pattern in the rounds feed.
            if let uploaderId = file.uploadedBy {
                ChannelAvatarView(
                    senderId: uploaderId,
                    payloadURL: file.uploaderAvatarUrl,
                    name: file.uploaderName ?? "",
                    size: 20
                )
            }
            if file.isImage, let url = URL(string: file.storageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().interpolation(.medium).aspectRatio(contentMode: .fill)
                    case .failure:
                        Color.zinc800.overlay(
                            Image(systemName: "photo").font(.system(size: 10)).foregroundColor(.secondary))
                    default:
                        Color.zinc800.overlay(ProgressView().controlSize(.small))
                    }
                }
                .frame(width: 30, height: 30)
                .clipShape(RoundedRectangle(cornerRadius: 4))
            } else {
                Image(systemName: "doc")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .frame(width: 30, height: 30)
            }
            Text(file.filename)
                .font(.system(size: 11))
                .foregroundColor(.mwInk)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer()
            Text(sizeLabel)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(isHovered ? Color.mwInk.opacity(0.08) : Color.mwInk.opacity(0.04))
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture(perform: onTap)
    }
}
