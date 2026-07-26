import SwiftUI
import PhotosUI

/// A photo/file selected in the composer but not yet uploaded. Uploaded to the
/// channel on send, then sent as a `ChannelAttachment` reference.
struct PendingAttachment: Identifiable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String
    var isImage: Bool { mimeType.hasPrefix("image/") }
}

/// Bottom message-input bar: reply banner, attachment thumbnails, photo picker,
/// growing text field, send button. Purely presentational — the parent owns the
/// optimistic send + upload.
struct MessageComposer: View {
    @Binding var text: String
    @Binding var replyingTo: ChannelMessage?
    @Binding var attachments: [PendingAttachment]
    var isUploading: Bool
    var onSend: () -> Void
    var onTyping: () -> Void

    @State private var photoItems: [PhotosPickerItem] = []

    private var canSend: Bool {
        !isUploading &&
        (!text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty)
    }

    var body: some View {
        VStack(spacing: 8) {
            if let reply = replyingTo {
                replyBanner(reply)
            }
            if !attachments.isEmpty {
                attachmentStrip
            }
            HStack(alignment: .bottom, spacing: 8) {
                PhotosPicker(selection: $photoItems, maxSelectionCount: 5, matching: .images) {
                    Image(systemName: "photo.on.rectangle")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
                .onChange(of: photoItems) { _, items in loadPhotos(items) }

                TextField("Message", text: $text, axis: .vertical)
                    .lineLimit(1...5)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(Color(.secondarySystemBackground)))
                    .onChange(of: text) { _, _ in onTyping() }

                Button(action: onSend) {
                    if isUploading {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                    }
                }
                .disabled(!canSend)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func replyBanner(_ reply: ChannelMessage) -> some View {
        HStack(spacing: 8) {
            Rectangle().fill(.tint).frame(width: 3).clipShape(Capsule())
            VStack(alignment: .leading, spacing: 1) {
                Text("Replying to \(reply.senderName)")
                    .font(.caption.bold()).foregroundStyle(.tint)
                Text(reply.content.isEmpty ? "Attachment" : reply.content)
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Button { replyingTo = nil } label: {
                Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 8)
    }

    private var attachmentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(attachments) { att in
                    ZStack(alignment: .topTrailing) {
                        if att.isImage, let img = UIImage(data: att.data) {
                            Image(uiImage: img).resizable().scaledToFill()
                                .frame(width: 60, height: 60)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        } else {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color(.secondarySystemBackground))
                                .frame(width: 60, height: 60)
                                .overlay(Image(systemName: "doc.fill").foregroundStyle(.secondary))
                        }
                        Button {
                            attachments.removeAll { $0.id == att.id }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.white, .black.opacity(0.5))
                        }
                        .padding(2)
                    }
                }
            }
            .padding(.horizontal, 4)
        }
    }

    private func loadPhotos(_ items: [PhotosPickerItem]) {
        guard !items.isEmpty else { return }
        Task {
            for item in items {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    let name = "image-\(UUID().uuidString.prefix(8)).jpg"
                    await MainActor.run {
                        attachments.append(PendingAttachment(data: data, filename: name, mimeType: "image/jpeg"))
                    }
                }
            }
            await MainActor.run { photoItems = [] }
        }
    }
}
