import SwiftUI
import AppKit

/// One pending image/file queued in the note composer before the note
/// is submitted. Held in memory only — uploaded to mw_project_files on
/// submit and linked to the activity row via metadata.attachment_ids.
struct PendingAttachment: Identifiable, Equatable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String

    var isImage: Bool { mimeType.lowercased().hasPrefix("image/") }
}

/// Chip rendered under the composer for each pending attachment. Click ×
/// to drop one before submitting. Shows a tiny thumbnail for images so
/// the user can confirm they grabbed the right screenshot.
struct PendingAttachmentChip: View {
    let attachment: PendingAttachment
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 5) {
            if attachment.isImage, let nsImg = NSImage(data: attachment.data) {
                Image(nsImage: nsImg)
                    .resizable()
                    .interpolation(.medium)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 22, height: 22)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
            } else {
                Image(systemName: attachment.isImage ? "photo" : "doc")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Text(attachment.filename)
                .font(.system(size: 10))
                .foregroundColor(.mwInk)
                .lineLimit(1)
                .truncationMode(.middle)
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Remove")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(Color.mwInk.opacity(0.06))
        .cornerRadius(4)
    }
}
