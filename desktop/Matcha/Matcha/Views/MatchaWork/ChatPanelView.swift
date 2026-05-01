import SwiftUI
import UniformTypeIdentifiers

private let resumeExtensions: Set<String> = ["pdf", "doc", "docx", "txt"]
private let inventoryExtensions: Set<String> = ["csv", "xlsx", "xls"]
private let imageExtensions: Set<String> = ["jpg", "jpeg", "png", "gif", "heic", "webp", "bmp", "tiff"]

struct ChatPanelView: View {
    @Bindable var viewModel: ThreadDetailViewModel
    var lightMode: Bool = false
    var selectedModel: String? = nil
    @State private var inputText = ""
    @State private var previewURL: String? = nil
    @State private var isDragOver = false
    @State private var uploadProgress: String? = nil

    // Matches server-side `SendMessageRequest.content` Field(max_length=4000)
    private static let messageCharLimit = 4000
    private var trimmedInputCount: Int {
        inputText.trimmingCharacters(in: .whitespacesAndNewlines).count
    }
    private var isOverLimit: Bool { trimmedInputCount > Self.messageCharLimit }

    private func send() {
        let content = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !viewModel.isStreaming, !isOverLimit else { return }
        inputText = ""
        Task { await viewModel.sendMessage(content: content, model: selectedModel) }
    }

    private var selectedSlideTitle: String? {
        guard let idx = viewModel.selectedSlideIndex,
              let raw = viewModel.currentState["slides"]?.value as? [AnyCodable],
              idx < raw.count,
              let dict = raw[idx].value as? [String: AnyCodable] else { return nil }
        return dict["title"]?.value as? String
    }

    private var inputPlaceholder: String {
        if let idx = viewModel.selectedSlideIndex {
            return "Edit slide \(idx + 1) — describe your changes..."
        }
        return "Message..."
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) {
        guard let threadId = viewModel.thread?.id else { return }
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                let ext = url.pathExtension.lowercased()
                guard let fileData = try? Data(contentsOf: url) else {
                    Task { @MainActor in viewModel.errorMessage = "Could not read \(url.lastPathComponent)" }
                    return
                }

                let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
                let file = (data: fileData, filename: url.lastPathComponent, mimeType: mime)

                if imageExtensions.contains(ext) {
                    Task { await self.uploadDroppedImage(file) }
                    return
                }

                let endpoint: String
                if resumeExtensions.contains(ext) {
                    endpoint = "resume/upload"
                } else if inventoryExtensions.contains(ext) {
                    endpoint = "inventory/upload"
                } else {
                    Task { @MainActor in
                        viewModel.errorMessage = "Unsupported file type: .\(ext). Supported: images, PDF/DOC/TXT (resumes), CSV/XLSX (inventory)."
                    }
                    return
                }

                Task {
                    await MainActor.run { uploadProgress = "Uploading \(url.lastPathComponent)..." }
                    do {
                        let bytes = try await MatchaWorkService.shared.uploadFiles(
                            threadId: threadId, endpoint: endpoint, files: [file]
                        )
                        for try await line in bytes.lines {
                            if line.hasPrefix("data: "), line.contains("\"type\":\"complete\"") || line.contains("[DONE]") {
                                break
                            }
                        }
                        await viewModel.loadThread(id: threadId)
                        await MainActor.run { uploadProgress = nil }
                    } catch {
                        await MainActor.run {
                            viewModel.errorMessage = "Upload failed: \(error.localizedDescription)"
                            uploadProgress = nil
                        }
                    }
                }
            }
        }
    }

    private func uploadDroppedImage(_ file: (data: Data, filename: String, mimeType: String)) async {
        if viewModel.presentationImageURLs.count >= 4 {
            await MainActor.run {
                viewModel.errorMessage = "Maximum 4 images per thread — remove one before adding more."
            }
            return
        }
        await MainActor.run { uploadProgress = "Uploading \(file.filename)..." }
        await viewModel.uploadImages([file])
        await MainActor.run { uploadProgress = nil }
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
                messagesArea
                Divider().opacity(0.3)
                if let err = viewModel.errorMessage {
                    Text(err)
                        .font(.system(size: 12))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(Color.red.opacity(0.1))
                }
                imageStrip
                slideBar
                jurisdictionBar
                if let progress = uploadProgress {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.mini)
                        Text(progress)
                            .font(.system(size: 11))
                            .foregroundColor(.matcha500)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.matcha500.opacity(0.06))
                }
                inputBar
            }
        }
        .overlay(
            isDragOver
            ? RoundedRectangle(cornerRadius: 8)
                .stroke(Color.matcha500, lineWidth: 2)
                .background(Color.matcha500.opacity(0.05))
                .allowsHitTesting(false)
            : nil
        )
        .onDrop(of: [.fileURL], isTargeted: $isDragOver) { providers in
            handleFileDrop(providers)
            return true
        }
        .background(Color.appBackground)
        .sheet(isPresented: Binding(get: { previewURL != nil }, set: { if !$0 { previewURL = nil } })) {
            if let url = previewURL {
                ImagePreviewSheet(url: url, onDismiss: { previewURL = nil })
            }
        }
    }

    @ViewBuilder private var messagesArea: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(viewModel.messages) { message in
                        MessageBubbleView(message: message, lightMode: lightMode)
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
    }

    @ViewBuilder private var imageStrip: some View {
        if !viewModel.presentationImageURLs.isEmpty || viewModel.isUploadingImages {
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
    }

    @ViewBuilder private var slideBar: some View {
        if let idx = viewModel.selectedSlideIndex {
            HStack(spacing: 6) {
                Image(systemName: "rectangle.on.rectangle")
                    .font(.system(size: 11))
                    .foregroundColor(.matcha500)
                let title = selectedSlideTitle
                Text("Slide \(idx + 1)\(title.map { ": \($0)" } ?? "")")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color.matcha500.opacity(0.85))
                Spacer()
                Button { viewModel.selectedSlideIndex = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Clear slide selection")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(Color.matcha500.opacity(0.08))
            .overlay(
                Rectangle()
                    .frame(height: 1)
                    .foregroundColor(Color.matcha500.opacity(0.2)),
                alignment: .top
            )
        }
    }

    @ViewBuilder private var jurisdictionBar: some View {
        if viewModel.thread?.complianceMode == true {
            HStack(spacing: 6) {
                Image(systemName: "mappin")
                    .font(.system(size: 11))
                    .foregroundColor(.cyan)
                Text("JURISDICTIONS")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if let meta = viewModel.messages.last(where: { $0.role == "assistant" })?.metadata,
                   let locs = meta.complianceReasoning, !locs.isEmpty {
                    ForEach(locs, id: \.locationId) { loc in
                        Text(loc.locationLabel)
                            .font(.system(size: 10))
                            .foregroundColor(.cyan)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.cyan.opacity(0.1))
                            .cornerRadius(4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 4)
                                    .stroke(Color.cyan.opacity(0.25), lineWidth: 1)
                            )
                    }
                } else {
                    Text("Active — locations will appear with responses")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(lightMode ? Color(white: 0.97) : Color.zinc900.opacity(0.5))
        }
    }

    private var imgAtLimit: Bool { viewModel.presentationImageURLs.count >= 4 }

    @ViewBuilder private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 10) {
            Button { pickImages() } label: {
                Image(systemName: "photo.badge.plus")
                    .font(.system(size: 17))
                    .foregroundColor(
                        imgAtLimit || viewModel.isUploadingImages
                        ? Color.secondary.opacity(0.35)
                        : .secondary
                    )
            }
            .buttonStyle(.plain)
            .disabled(imgAtLimit || viewModel.isUploadingImages)
            .help(
                imgAtLimit
                ? "Maximum 4 images per thread"
                : "Upload images (\(viewModel.presentationImageURLs.count)/4)"
            )

            TextField(inputPlaceholder, text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundColor(.white)
                .lineLimit(1...6)
                .padding(.vertical, 8)
                .onChange(of: inputText) { _, newValue in
                    // Hard cap: trim past the limit so paste-bombs can't bypass send-disable
                    if newValue.count > Self.messageCharLimit {
                        inputText = String(newValue.prefix(Self.messageCharLimit))
                    }
                }
                .onKeyPress(keys: [.return], phases: .down) { press in
                    if press.modifiers.contains(.shift) {
                        inputText += "\n"
                        return .handled
                    }
                    send()
                    return .handled
                }

            if trimmedInputCount > Self.messageCharLimit - 500 {
                Text("\(trimmedInputCount)/\(Self.messageCharLimit)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(isOverLimit ? .red : .secondary)
                    .help("Messages are capped at \(Self.messageCharLimit) characters")
            }

            Button { send() } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .foregroundColor(
                        inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isOverLimit
                        ? .secondary : .matcha500
                    )
            }
            .buttonStyle(.plain)
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isStreaming || isOverLimit)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.zinc900)
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
