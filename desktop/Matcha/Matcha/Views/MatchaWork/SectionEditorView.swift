import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct SectionEditorView: View {
    let section: MWProjectSection
    let onSave: (String?, String?) -> Void
    var onAcceptRevision: (() -> Void)? = nil
    var onRejectRevision: (() -> Void)? = nil
    var onRestore: ((String) -> Void)? = nil
    /// Project id for blog-media uploads. When nil the image / video toolbar
    /// buttons are disabled (callers that don't expose a project context can
    /// omit this).
    var projectId: String? = nil

    @State private var title: String = ""
    @State private var content: String = ""
    @State private var saveTimer: Timer?
    @State private var isSaved = false
    @State private var hasUnsavedChanges = false
    @State private var showPendingPreview = true
    @State private var controller = MarkdownEditorController()
    @State private var uploadStatus: String? = nil
    @State private var uploadError: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            // Title
            TextField("Section title", text: $title)
                .textFieldStyle(.plain)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 8)
                .onChange(of: title) { scheduleSave() }

            Divider().opacity(0.2).padding(.horizontal, 20)

            if section.hasPendingRevision {
                pendingRevisionBanner
            }

            formattingToolbar

            // Content editor
            MarkdownTextEditor(text: $content, controller: $controller)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .onChange(of: content) { scheduleSave() }

            // Footer
            HStack(spacing: 12) {
                Text("Markdown supported")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                if let status = uploadStatus {
                    Text(status)
                        .font(.system(size: 10))
                        .foregroundColor(.matcha500)
                }
                if let err = uploadError {
                    Text(err)
                        .font(.system(size: 10))
                        .foregroundColor(.red)
                        .lineLimit(1)
                }
                Spacer()
                historyMenu
                if isSaved {
                    Text("Saved")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(.matcha500)
                        .transition(.opacity)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 8)
            .background(Color.zinc800.opacity(0.3))
        }
        .background(Color(white: 0.11))
        .onAppear {
            title = section.title
            content = section.content ?? ""
            hasUnsavedChanges = false
        }
        .onChange(of: section.id) {
            // Different section — flush any pending save for the prior one.
            flushSaveIfDirty()
            title = section.title
            content = section.content ?? ""
            isSaved = false
            hasUnsavedChanges = false
            showPendingPreview = true
        }
        .onDisappear {
            flushSaveIfDirty()
        }
    }

    /// Fires an immediate synchronous-ish save if there are unsaved edits,
    /// bypassing the 1s debounce. Called on view disappear and section switch
    /// so user text is durable before any sibling action (chat send, tab
    /// change) can trigger an AI revision against stale content.
    private func flushSaveIfDirty() {
        saveTimer?.invalidate()
        saveTimer = nil
        guard hasUnsavedChanges else { return }
        let t = title.isEmpty ? nil : title
        onSave(t, content)
        hasUnsavedChanges = false
    }

    private var pendingRevisionBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                Text("AI suggestion")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                if let summary = section.pendingChangeSummary, !summary.isEmpty {
                    Text("— \(summary)")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                Button {
                    showPendingPreview.toggle()
                } label: {
                    Image(systemName: showPendingPreview ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                Button("Reject") { onRejectRevision?() }
                    .font(.system(size: 11, weight: .medium))
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.zinc800)
                    .cornerRadius(5)
                Button("Accept") { onAcceptRevision?() }
                    .font(.system(size: 11, weight: .semibold))
                    .buttonStyle(.plain)
                    .foregroundColor(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.matcha600)
                    .cornerRadius(5)
            }

            if showPendingPreview, let pending = section.pendingRevision, !pending.isEmpty {
                ScrollView {
                    Text(pending)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(Color(white: 0.85))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                }
                .frame(maxHeight: 180)
                .background(Color.black.opacity(0.25))
                .cornerRadius(6)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(Color.matcha600.opacity(0.08))
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundColor(Color.matcha600.opacity(0.3)),
            alignment: .bottom
        )
    }

    @ViewBuilder
    private var historyMenu: some View {
        let entries = section.history ?? []
        if !entries.isEmpty {
            Menu {
                ForEach(entries.reversed()) { entry in
                    Button {
                        onRestore?(entry.content)
                    } label: {
                        Text("\(formatHistoryTime(entry.at)) · \(entry.source ?? "user") (\(entry.content.split(separator: " ").count) words)")
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "clock.arrow.circlepath").font(.system(size: 10))
                    Text("History (\(entries.count))").font(.system(size: 10, weight: .medium))
                }
                .foregroundColor(.secondary)
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Color.zinc800)
                .cornerRadius(5)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Restore an earlier version of this section")
        }
    }

    private func formatHistoryTime(_ iso: String) -> String {
        let isoFmt = ISO8601DateFormatter()
        isoFmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = isoFmt.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        guard let d = date else { return iso }
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d, h:mm a"
        return fmt.string(from: d)
    }

    private func scheduleSave() {
        isSaved = false
        hasUnsavedChanges = true
        saveTimer?.invalidate()
        saveTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: false) { _ in
            let t = title.isEmpty ? nil : title
            let c = content
            onSave(t, c)
            hasUnsavedChanges = false
            Task { @MainActor in
                withAnimation { isSaved = true }
                try? await Task.sleep(for: .seconds(2))
                withAnimation { isSaved = false }
            }
        }
    }

    // MARK: - Formatting toolbar

    @ViewBuilder
    private var formattingToolbar: some View {
        HStack(spacing: 3) {
            toolbarButton("B", bold: true, help: "Bold") {
                controller.wrapSelection(left: "**", right: "**", placeholder: "bold")
            }
            toolbarButton("I", italic: true, help: "Italic") {
                controller.wrapSelection(left: "*", right: "*", placeholder: "italic")
            }
            toolbarButton("H1", help: "Heading 1") {
                controller.prefixLines(with: "# ")
            }
            toolbarButton("H2", help: "Heading 2") {
                controller.prefixLines(with: "## ")
            }
            toolbarIcon("list.bullet", help: "Bulleted list") {
                controller.prefixLines(with: "- ")
            }
            toolbarIcon("list.number", help: "Numbered list") {
                controller.prefixLines(with: "1. ")
            }
            toolbarIcon("text.quote", help: "Quote") {
                controller.prefixLines(with: "> ")
            }
            toolbarIcon("chevron.left.forwardslash.chevron.right", help: "Inline code") {
                controller.wrapSelection(left: "`", right: "`", placeholder: "code")
            }
            toolbarIcon("link", help: "Link") {
                controller.wrapSelection(left: "[", right: "](https://)", placeholder: "text")
            }
            Divider().frame(height: 14).padding(.horizontal, 2)
            toolbarIcon("photo", help: projectId == nil ? "Image (no project)" : "Insert image (max 50 MB)") {
                pickMedia(kind: .image)
            }
            .disabled(projectId == nil)
            toolbarIcon("video", help: projectId == nil ? "Video (no project)" : "Insert video (max 50 MB)") {
                pickMedia(kind: .video)
            }
            .disabled(projectId == nil)
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 6)
        .background(Color.zinc800.opacity(0.35))
        .overlay(
            Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.08)),
            alignment: .bottom
        )
    }

    @ViewBuilder
    private func toolbarButton(_ label: String, bold: Bool = false, italic: Bool = false, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: bold ? .bold : .medium, design: .default))
                .italic(italic)
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }

    @ViewBuilder
    private func toolbarIcon(_ systemName: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 11))
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }

    // MARK: - Media upload

    private enum MediaKind { case image, video }

    private func pickMedia(kind: MediaKind) {
        guard projectId != nil else { return }
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        switch kind {
        case .image:
            panel.allowedContentTypes = [.png, .jpeg, .gif, .webP, .heic, .svg]
        case .video:
            panel.allowedContentTypes = [.movie, .video, .quickTimeMovie, .mpeg4Movie]
        }
        panel.begin { response in
            guard response == .OK, let url = panel.urls.first else { return }
            Task { await uploadAndInsert(url: url, kind: kind) }
        }
    }

    private func uploadAndInsert(url: URL, kind: MediaKind) async {
        guard let pid = projectId else { return }
        guard let data = try? Data(contentsOf: url) else {
            await MainActor.run { uploadError = "Couldn't read file" }
            return
        }
        if data.count > 50 * 1024 * 1024 {
            await MainActor.run { uploadError = "File exceeds 50 MB" }
            return
        }
        let ext = url.pathExtension.lowercased()
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? (kind == .image ? "image/png" : "video/mp4")
        await MainActor.run {
            uploadStatus = "Uploading \(url.lastPathComponent)…"
            uploadError = nil
        }
        do {
            let uploaded = try await MatchaWorkService.shared.uploadBlogMedia(
                projectId: pid,
                file: (data: data, filename: url.lastPathComponent, mimeType: mime)
            )
            await MainActor.run {
                let snippet: String
                switch kind {
                case .image:
                    snippet = "![\(url.deletingPathExtension().lastPathComponent)](\(uploaded.url))"
                case .video:
                    snippet = "<video src=\"\(uploaded.url)\" controls width=\"100%\"></video>"
                }
                controller.insertBlock(snippet)
                uploadStatus = nil
            }
        } catch {
            await MainActor.run {
                uploadStatus = nil
                uploadError = error.localizedDescription
            }
        }
    }
}
