import SwiftUI
import UniformTypeIdentifiers

struct ChatPanelView: View {
    @Bindable var viewModel: ThreadDetailViewModel
    @State private var inputText = ""
    @State private var previewURL: String? = nil

    private var isWorkbook: Bool { viewModel.thread?.taskType == "workbook" }

    private func send() {
        let content = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !viewModel.isStreaming else { return }
        inputText = ""
        Task { await viewModel.sendMessage(content: content) }
    }

    private func pickImages() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.jpeg, .png, .gif, .heic, .webP, .bmp, .tiff]
        let remaining = 4 - viewModel.presentationImageURLs.count
        panel.begin { response in
            guard response == .OK else { return }
            let selected = Array(panel.urls.prefix(remaining))
            Task {
                var images: [(data: Data, filename: String, mimeType: String)] = []
                for url in selected {
                    guard let data = try? Data(contentsOf: url) else { continue }
                    let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "image/jpeg"
                    images.append((data: data, filename: url.lastPathComponent, mimeType: mime))
                }
                if !images.isEmpty {
                    await viewModel.uploadImages(images)
                }
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if viewModel.isLoadingThread {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.messages) { message in
                                MessageBubbleView(message: message)
                                    .id(message.id)
                            }
                            if viewModel.isStreaming {
                                StreamingBubbleView(content: viewModel.streamingContent)
                                    .id("streaming")
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                    }
                    .onChange(of: viewModel.messages.count) {
                        if let lastId = viewModel.messages.last?.id {
                            withAnimation(.easeOut(duration: 0.2)) {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                    .onChange(of: viewModel.isStreaming) {
                        if viewModel.isStreaming {
                            withAnimation { proxy.scrollTo("streaming", anchor: .bottom) }
                        }
                    }
                }

                Divider().opacity(0.3)

                // Error banner
                if let err = viewModel.errorMessage {
                    Text(err)
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(Color.red.opacity(0.1))
                }

                // Image strip — workbook threads only
                if isWorkbook && (!viewModel.presentationImageURLs.isEmpty || viewModel.isUploadingImages) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(viewModel.presentationImageURLs, id: \.self) { url in
                                ImageThumbnailView(
                                    url: url,
                                    onPreview: { previewURL = url },
                                    onRemove: { Task { await viewModel.removeImage(url: url) } }
                                )
                            }

                            if viewModel.isUploadingImages {
                                ZStack {
                                    Color.zinc800.cornerRadius(6)
                                    ProgressView().controlSize(.small)
                                }
                                .frame(width: 64, height: 64)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                    .background(Color.zinc900)
                    Divider().opacity(0.3)
                }

                // Input area
                HStack(alignment: .bottom, spacing: 10) {
                    // Image attach button — workbook threads only
                    if isWorkbook {
                        Button { pickImages() } label: {
                            Image(systemName: "photo")
                                .font(.system(size: 16))
                                .foregroundColor(
                                    viewModel.presentationImageURLs.count >= 4 || viewModel.isUploadingImages
                                    ? Color.secondary.opacity(0.4)
                                    : .secondary
                                )
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.presentationImageURLs.count >= 4 || viewModel.isUploadingImages)
                        .help(
                            viewModel.presentationImageURLs.count >= 4
                            ? "Maximum 4 images"
                            : "Add images for presentation (\(viewModel.presentationImageURLs.count)/4)"
                        )
                    }

                    TextField("Message...", text: $inputText, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .foregroundColor(.white)
                        .lineLimit(1...6)
                        .padding(.vertical, 8)
                        .onSubmit { send() }

                    Button { send() } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 28))
                            .foregroundColor(
                                inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? .secondary : .matcha500
                            )
                    }
                    .buttonStyle(.plain)
                    .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isStreaming)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color.zinc900)
            }
        }
        .background(Color.appBackground)
        .sheet(isPresented: Binding(get: { previewURL != nil }, set: { if !$0 { previewURL = nil } })) {
            if let url = previewURL {
                ImagePreviewSheet(url: url, onDismiss: { previewURL = nil })
            }
        }
    }
}

// MARK: - Thumbnail

private struct ImageThumbnailView: View {
    let url: String
    let onPreview: () -> Void
    let onRemove: () -> Void
    @State private var isHovered = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Button(action: onPreview) {
                AsyncImage(url: URL(string: url)) { phase in
                    if let img = phase.image {
                        img.resizable().scaledToFill()
                    } else {
                        Color.zinc800
                    }
                }
                .frame(width: 72, height: 72)
                .clipped()
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isHovered ? Color.white.opacity(0.4) : Color.clear, lineWidth: 1.5)
                )
                .scaleEffect(isHovered ? 1.03 : 1.0)
                .animation(.easeOut(duration: 0.12), value: isHovered)
            }
            .buttonStyle(.plain)
            .onHover { isHovered = $0 }
            .help("Click to preview")

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(.white, Color.black.opacity(0.7))
            }
            .buttonStyle(.plain)
            .offset(x: 5, y: -5)
        }
    }
}

// MARK: - Full-size preview sheet

private struct ImagePreviewSheet: View {
    let url: String
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button("Done", action: onDismiss)
                    .buttonStyle(.plain)
                    .foregroundColor(.matcha500)
                    .font(.system(size: 13, weight: .medium))
                    .padding(16)
            }

            AsyncImage(url: URL(string: url)) { phase in
                switch phase {
                case .success(let img):
                    img.resizable()
                        .scaledToFit()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .failure:
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 32))
                            .foregroundColor(.secondary)
                        Text("Failed to load image")
                            .foregroundColor(.secondary)
                            .font(.system(size: 13))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                default:
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
        .frame(minWidth: 480, minHeight: 400)
        .background(Color.appBackground)
    }
}
