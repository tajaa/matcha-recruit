import SwiftUI
import UniformTypeIdentifiers

private let imageExtensions: Set<String> = ["jpg", "jpeg", "png", "gif", "heic", "webp", "bmp", "tiff"]
// Non-image files that attach to a message as plain reference material. The
// AI only reads them when the user's message gives an instruction; a file
// sent with no text yields a clarifying reply (server-side guardrail).
private let attachableExtensions: Set<String> = ["pdf", "doc", "docx", "txt", "md", "csv", "json"]
private let maxPendingFiles = 5
private let maxFileBytes = 10 * 1024 * 1024

struct ChatPanelView: View {
    @Environment(AppState.self) private var appState
    @Bindable var viewModel: ThreadDetailViewModel
    var lightMode: Bool = false
    var selectedModel: String? = nil
    @State private var inputText = ""

    private var greetingText: String {
        let name: String
        if let user = appState.currentUser {
            if let fullName = user.name, !fullName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let parts = fullName.split(separator: " ")
                if let first = parts.first {
                    name = String(first)
                } else {
                    name = fullName
                }
            } else {
                let emailParts = user.email.split(separator: "@")
                if let firstPart = emailParts.first {
                    name = String(firstPart).capitalized
                } else {
                    name = "there"
                }
            }
        } else {
            name = "there"
        }
        return "Hi, \(name). What should we do today?"
    }
    @State private var previewURL: String? = nil
    @State private var isDragOver = false
    @State private var uploadProgress: String? = nil
    @State private var pendingFiles: [(data: Data, filename: String, mimeType: String)] = []
    /// True while the bottom sentinel is on screen — gates message auto-scroll.
    @State private var isAtBottom = true

    // Matches server-side `SendMessageRequest.content` Field(max_length=4000)
    private static let messageCharLimit = 4000
    private var trimmedInputCount: Int {
        inputText.trimmingCharacters(in: .whitespacesAndNewlines).count
    }
    private var isOverLimit: Bool { trimmedInputCount > Self.messageCharLimit }

    private func send() {
        var content = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let files = pendingFiles
        // Allow sending with files but no text — server replies asking what the
        // user wants rather than auto-analyzing.
        guard (!content.isEmpty || !files.isEmpty), !viewModel.isStreaming, !isOverLimit else { return }
        // Weave in a referenced ticket (from "Chat about this ticket") as a
        // compact reply-style prefix so the sent message reads like a reply and
        // the AI gets the ticket as context. Captured + cleared on send.
        if let ref = appState.pendingTicketRef {
            let colLabel = ref.column.replacingOccurrences(of: "_", with: " ").capitalized
            let prefix = "Re: ticket “\(ref.title)” (\(colLabel))"
            content = content.isEmpty ? prefix : "\(prefix)\n\n\(content)"
            appState.pendingTicketRef = nil
        }
        inputText = ""
        pendingFiles = []
        Task {
            var attachments: [MWMessageAttachment] = []
            if !files.isEmpty, let threadId = viewModel.thread?.id {
                await MainActor.run {
                    uploadProgress = "Uploading \(files.count) file\(files.count == 1 ? "" : "s")..."
                }
                do {
                    attachments = try await MatchaWorkService.shared.uploadThreadFiles(
                        threadId: threadId, files: files
                    )
                } catch {
                    await MainActor.run {
                        viewModel.errorMessage = "Upload failed: \(error.localizedDescription)"
                        uploadProgress = nil
                        // Restore the dropped files so the user can retry.
                        pendingFiles = files
                    }
                    return
                }
                await MainActor.run { uploadProgress = nil }
            }
            await viewModel.sendMessage(content: content, model: selectedModel, fileAttachments: attachments)
        }
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

    @ViewBuilder
    private var pendingFilesStrip: some View {
        if !pendingFiles.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(Array(pendingFiles.enumerated()), id: \.offset) { idx, file in
                        HStack(spacing: 6) {
                            Image(systemName: "doc")
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeAccent)
                            Text(file.filename)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeText)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Button {
                                pendingFiles.remove(at: idx)
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 8))
                                    .foregroundColor(appState.themeTextSecondary)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(appState.themeCard)
                        .cornerRadius(6)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 4)
            }
        }
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) {
        guard viewModel.thread != nil else { return }
        for provider in providers {
            provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                guard let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                ingest(url: url)
            }
        }
    }

    /// Shared intake for the drop handler AND the file picker: images go to
    /// the thread's image set, attachable docs (PDF/DOC/TXT/MD/CSV/JSON) queue
    /// as pending chips. The file is NOT analyzed on attach — it uploads +
    /// feeds the AI only when the user sends a message with it (server
    /// guardrail handles the no-instruction case with a clarifying reply).
    private func ingest(url: URL) {
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

        guard attachableExtensions.contains(ext) else {
            Task { @MainActor in
                viewModel.errorMessage = "Unsupported file type: .\(ext). Supported: images, PDF, DOC/DOCX, TXT, MD, CSV, JSON."
            }
            return
        }

        Task { @MainActor in
            if pendingFiles.count >= maxPendingFiles {
                viewModel.errorMessage = "Up to \(maxPendingFiles) files per message."
                return
            }
            if fileData.count > maxFileBytes {
                viewModel.errorMessage = "\(file.filename) exceeds 10 MB."
                return
            }
            pendingFiles.append(file)
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

    /// Attach via the file picker. Was image-only (`allowedContentTypes` of
    /// image UTTypes) which made CSV/PDF/DOC unpickable even though drag-drop
    /// accepted them — now any file is selectable and routed through the same
    /// `ingest(url:)` the drop handler uses (extension-validated there).
    private func pickFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsOtherFileTypes = true   // allow any type; validated on ingest
        panel.begin { response in
            guard response == .OK else { return }
            for url in panel.urls {
                ingest(url: url)
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if viewModel.isLoadingThread {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if viewModel.messages.isEmpty {
                emptyThreadMiddleView
            } else {
                messagesArea
                Divider().opacity(0.3)
                if let err = viewModel.errorMessage {
                    HStack(spacing: 8) {
                        Text(err)
                            .font(.system(size: 12))
                            .foregroundColor(viewModel.quotaExhausted ? appState.themeText : .red)
                        if viewModel.quotaExhausted {
                            // Rolling AI quota hit — upsell, not an error.
                            Button("Upgrade for more") {
                                appState.presentPaywall(for: "ai_quota")
                            }
                            .buttonStyle(.plain)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(appState.themeAccent)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 6)
                    .background(viewModel.quotaExhausted
                                ? appState.themeAccent.opacity(0.08)
                                : Color.red.opacity(0.1))
                }
                imageStrip
                slideBar
                jurisdictionBar
                if let progress = uploadProgress {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.mini)
                        Text(progress)
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeAccent)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(appState.themeAccent.opacity(0.06))
                }
                pendingFilesStrip
                ticketRefBar
                inputBar
            }
        }
        .overlay(
            isDragOver
            ? RoundedRectangle(cornerRadius: 8)
                .stroke(appState.themeAccent, lineWidth: 2)
                .background(appState.themeAccent.opacity(0.05))
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
                    // Bottom sentinel — visible only when the user is scrolled to
                    // the end. Gates auto-scroll so new messages don't yank the
                    // view down while the user is reading history (macOS 14 has no
                    // onScrollGeometryChange, so we detect via appear/disappear).
                    Color.clear
                        .frame(height: 1)
                        .id("__bottom_anchor")
                        .onAppear { isAtBottom = true }
                        .onDisappear { isAtBottom = false }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            // Always follow new messages to the bottom. The isAtBottom gate was
            // unreliable (the lazy sentinel's appear/disappear mis-fires — same
            // finding as ChannelDetailView), so sends/replies often landed
            // off-screen. Chat-standard: a new message always reveals itself.
            .onChange(of: viewModel.messages.count) {
                guard let lastId = viewModel.messages.last?.id else { return }
                withAnimation(.easeOut(duration: 0.2)) {
                    proxy.scrollTo(lastId, anchor: .bottom)
                }
            }
            .onChange(of: viewModel.isStreaming) {
                // No animation during streaming — token-rate scrolls churn the
                // main thread. Streaming starts right after a send, so always
                // bring the streaming bubble into view.
                if viewModel.isStreaming {
                    proxy.scrollTo("streaming", anchor: .bottom)
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
                            appState.themeCard.cornerRadius(6)
                            ProgressView().controlSize(.small)
                        }
                        .frame(width: 64, height: 64)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .background(appState.themeCard)
            Divider().opacity(0.3)
        }
    }

    @ViewBuilder private var slideBar: some View {
        if let idx = viewModel.selectedSlideIndex {
            HStack(spacing: 6) {
                Image(systemName: "rectangle.on.rectangle")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                let title = selectedSlideTitle
                Text("Slide \(idx + 1)\(title.map { ": \($0)" } ?? "")")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeAccent.opacity(0.85))
                Spacer()
                Button { viewModel.selectedSlideIndex = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Clear slide selection")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(appState.themeAccent.opacity(0.08))
            .overlay(
                Rectangle()
                    .frame(height: 1)
                    .foregroundColor(appState.themeAccent.opacity(0.2)),
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
                    .foregroundColor(appState.themeTextSecondary)
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
                        .foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(appState.themeCard.opacity(0.5))
        }
    }

    /// Reply-style banner shown above the composer when a kanban ticket was
    /// sent here via "Chat about this ticket". Mirrors the slide/jurisdiction
    /// context bars; × clears the reference without sending.
    @ViewBuilder private var ticketRefBar: some View {
        if let ref = appState.pendingTicketRef {
            HStack(spacing: 6) {
                Image(systemName: "arrowshape.turn.up.left.fill")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeAccent)
                Text("Chatting about")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                Text(ref.title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
                    .lineLimit(1)
                Text(ref.column.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeCard)
                    .cornerRadius(4)
                Spacer()
                Button { appState.pendingTicketRef = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Stop referencing this ticket")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 6)
            .background(appState.themeAccent.opacity(0.08))
            .overlay(
                Rectangle()
                    .frame(height: 1)
                    .foregroundColor(appState.themeAccent.opacity(0.2)),
                alignment: .top
            )
        }
    }

    @ViewBuilder private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 10) {
            Button { pickFiles() } label: {
                Image(systemName: "paperclip")
                    .font(.system(size: 17))
                    .foregroundColor(
                        viewModel.isUploadingImages
                        ? Color.secondary.opacity(0.35)
                        : .secondary
                    )
            }
            .buttonStyle(.plain)
            .disabled(viewModel.isUploadingImages)
            .help("Attach files — images, PDF, DOC/DOCX, TXT, MD, CSV, JSON")

            TextField(inputPlaceholder, text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundColor(appState.themeText)
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
                        ? appState.themeTextSecondary : appState.themeAccent
                    )
            }
            .buttonStyle(.plain)
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isStreaming || isOverLimit)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(appState.themeCard)
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
                        Color.cardBackground
                    }
                }
                .frame(width: 72, height: 72)
                .clipped()
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isHovered ? Color.borderColor : Color.clear, lineWidth: 1.5)
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

// MARK: - Center/Empty thread views & components

extension ChatPanelView {
    @ViewBuilder private var suggestionCards: some View {
        if viewModel.currentTaskType == .presentation {
            SuggestionCard(
                title: "Create a slide deck",
                icon: "rectangle.on.rectangle",
                text: "Build a presentation with slides and speaker notes",
                lightMode: lightMode
            ) { inputText = "Create a presentation on this topic with slides and speaker notes." }
            SuggestionCard(
                title: "Executive summary",
                icon: "chart.bar.doc.horizontal",
                text: "One-pager summarizing key metrics and decisions",
                lightMode: lightMode
            ) { inputText = "Create a 1-page executive summary presentation with key highlights." }
            SuggestionCard(
                title: "Pitch deck",
                icon: "arrow.up.forward.circle.fill",
                text: "Persuasive slides for a pitch or proposal",
                lightMode: lightMode
            ) { inputText = "Build a pitch deck with problem, solution, market, and ask slides." }
        } else {
            SuggestionCard(
                title: "Draft an offer letter",
                icon: "doc.text.fill",
                text: "Create a job offer letter for a Software Engineer candidate",
                lightMode: lightMode
            ) { inputText = "Draft an offer letter for a Software Engineer candidate named Jane." }
            SuggestionCard(
                title: "Performance review",
                icon: "star.fill",
                text: "Write a performance review highlighting key accomplishments",
                lightMode: lightMode
            ) { inputText = "Write a performance review highlighting key achievements and growth areas." }
            SuggestionCard(
                title: "Onboarding workbook",
                icon: "book.fill",
                text: "Build an onboarding guide or workbook for a new hire",
                lightMode: lightMode
            ) { inputText = "Create an onboarding workbook for a new engineer starting next week." }
        }
    }

    @ViewBuilder private var emptyThreadMiddleView: some View {
        VStack(spacing: 0) {
            Spacer()
            
            VStack(spacing: 24) {
                Text(greetingText)
                    .font(.system(size: 26, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
                
                VStack(alignment: .leading, spacing: 8) {
                    if let err = viewModel.errorMessage {
                        Text(err)
                            .font(.system(size: 12))
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(Color.red.opacity(0.1))
                            .cornerRadius(8)
                    }
                    
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
                                        appState.themeCard.cornerRadius(6)
                                        ProgressView().controlSize(.small)
                                    }
                                    .frame(width: 64, height: 64)
                                }
                            }
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 4)
                    }

                    if let progress = uploadProgress {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.mini)
                            Text(progress)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeAccent)
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 4)
                    }
                    
                    if !pendingFiles.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(Array(pendingFiles.enumerated()), id: \.offset) { idx, file in
                                    HStack(spacing: 6) {
                                        Image(systemName: "doc")
                                            .font(.system(size: 11))
                                            .foregroundColor(appState.themeAccent)
                                        Text(file.filename)
                                            .font(.system(size: 11))
                                            .foregroundColor(appState.themeText)
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                        Button {
                                            pendingFiles.remove(at: idx)
                                        } label: {
                                            Image(systemName: "xmark")
                                                .font(.system(size: 8))
                                                .foregroundColor(appState.themeTextSecondary)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 5)
                                    .background(appState.themeCard)
                                    .cornerRadius(6)
                                }
                            }
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 4)
                    }
                    
                    ticketRefBar

                    HStack(alignment: .bottom, spacing: 10) {
                        Button { pickFiles() } label: {
                            Image(systemName: "paperclip")
                                .font(.system(size: 17))
                                .foregroundColor(
                                    viewModel.isUploadingImages
                                    ? Color.secondary.opacity(0.35)
                                    : .secondary
                                )
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isUploadingImages)
                        .help("Attach files — images, PDF, DOC/DOCX, TXT, MD, CSV, JSON")

                        TextField(inputPlaceholder, text: $inputText, axis: .vertical)
                            .textFieldStyle(.plain)
                            .font(.system(size: 14))
                            .foregroundColor(appState.themeText)
                            .lineLimit(1...6)
                            .padding(.vertical, 8)
                            .onChange(of: inputText) { _, newValue in
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
                        }

                        Button { send() } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 28))
                                .foregroundColor(
                                    inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isOverLimit
                                    ? appState.themeTextSecondary : appState.themeAccent
                                )
                        }
                        .buttonStyle(.plain)
                        .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isStreaming || isOverLimit)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(appState.themeCard)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(appState.themeBorder, lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.15), radius: 8, x: 0, y: 4)
                .frame(maxWidth: 560)
                
                HStack(spacing: 12) {
                    suggestionCards
                }
                .frame(maxWidth: 560)
            }
            .padding(.horizontal, 24)
            
            Spacer()
        }
        // Fill the pane so the centered hero/composer block sits in the middle.
        // Without this the VStack shrink-wraps to its ~560pt content width and a
        // parent left-aligns it — pinning the new-chat landing to the left edge
        // (visible in a bottom/side split pane).
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Suggestion Card Component

struct SuggestionCard: View {
    let title: String
    let icon: String
    let text: String
    let lightMode: Bool
    let action: () -> Void
    @State private var isHovered = false
    
    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.system(size: 11))
                        .foregroundColor(.matcha500)
                    Text(title)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.primary)
                }
                Text(text)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
            }
            .padding(10)
            .frame(maxWidth: .infinity, minHeight: 72, alignment: .topLeading)
            .background(isHovered ? Color.cardBackground.opacity(0.7) : Color.cardBackground)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.borderColor, lineWidth: 1)
            )
            .scaleEffect(isHovered ? 1.02 : 1.0)
            .animation(.easeOut(duration: 0.12), value: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
    }
}
