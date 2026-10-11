import SwiftUI

/// An image attached to a message: cropped to fill, with an expand hint on
/// hover. Clicking opens the larger preview.
struct AttachmentImageTile: View {
    let url: String
    var height: CGFloat = 120
    let onOpen: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: onOpen) {
            AsyncImage(url: URL(string: url)) { phase in
                switch phase {
                case .success(let img):
                    img.resizable().scaledToFill()
                case .failure:
                    Image(systemName: "photo")
                        .foregroundColor(.white.opacity(0.4))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(Color.black.opacity(0.15))
                default:
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(Color.black.opacity(0.15))
                }
            }
            .frame(height: height)
            .frame(maxWidth: .infinity)
            .clipped()
            .overlay {
                if hovering {
                    ZStack(alignment: .bottomTrailing) {
                        LinearGradient(colors: [.clear, .black.opacity(0.45)], startPoint: .center, endPoint: .bottom)
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                            .frame(width: 22, height: 22)
                            .background(Circle().fill(Color.black.opacity(0.45)))
                            .padding(7)
                    }
                    .transition(.opacity)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .animation(.easeOut(duration: 0.12), value: hovering)
        .help("Click to view larger and download")
    }
}

/// A file attached to a message, as a small card: a type glyph, the name and
/// the size. `onAccent` is for the user's own (accent-filled) bubble.
struct AttachmentFileCard: View {
    @Environment(AppState.self) private var appState
    let attachment: MWMessageAttachment
    var onAccent = false
    @State private var hovering = false

    private var fileExtension: String {
        ((attachment.filename ?? attachment.url) as NSString).pathExtension.lowercased()
    }

    private var glyph: (icon: String, tint: Color) {
        switch fileExtension {
        case "pdf": return ("doc.richtext", Color(red: 0.90, green: 0.30, blue: 0.27))
        case "csv", "xlsx", "xls": return ("tablecells", Color(red: 0.20, green: 0.64, blue: 0.40))
        case "doc", "docx": return ("doc.text", Color(red: 0.25, green: 0.50, blue: 0.95))
        case "json": return ("curlybraces", Color(red: 0.62, green: 0.45, blue: 0.95))
        case "md", "txt": return ("doc.plaintext", Color(red: 0.50, green: 0.53, blue: 0.60))
        default: return ("doc", Color(red: 0.50, green: 0.53, blue: 0.60))
        }
    }

    private var sizeText: String? {
        guard let size = attachment.size, size > 0 else { return nil }
        return ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file)
    }

    var body: some View {
        let ink = onAccent ? Color.white : appState.themeText
        let detail = [fileExtension.isEmpty ? nil : fileExtension.uppercased(), sizeText]
            .compactMap { $0 }.joined(separator: " · ")
        Button { SafeURL.open(attachment.url) } label: {
            HStack(spacing: 9) {
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(onAccent ? Color.white.opacity(0.22) : glyph.tint.opacity(0.16))
                    .frame(width: 30, height: 30)
                    .overlay(
                        Image(systemName: glyph.icon)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(onAccent ? .white : glyph.tint)
                    )
                VStack(alignment: .leading, spacing: 1) {
                    Text(attachment.filename ?? "file")
                        .font(.espresso(size: 12, weight: .medium))
                        .foregroundColor(ink)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if !detail.isEmpty {
                        Text(detail)
                            .font(.espresso(size: 10.5))
                            .foregroundColor(ink.opacity(0.6))
                    }
                }
                Spacer(minLength: 4)
                Image(systemName: "arrow.down.circle")
                    .font(.system(size: 13))
                    .foregroundColor(ink.opacity(hovering ? 0.9 : 0.45))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 7)
            .frame(maxWidth: 300, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(onAccent ? Color.white.opacity(hovering ? 0.2 : 0.13) : appState.themeCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(onAccent ? Color.white.opacity(0.18) : (hovering ? glyph.tint.opacity(0.5) : appState.themeBorder),
                            lineWidth: 0.5)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help("Open \(attachment.filename ?? "file")")
    }
}
