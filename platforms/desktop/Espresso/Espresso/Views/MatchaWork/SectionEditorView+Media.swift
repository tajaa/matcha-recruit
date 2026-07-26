import SwiftUI
import UniformTypeIdentifiers
import AppKit

// MARK: - Image / video upload and insert
//
// Split out of SectionEditorView.swift. Driven by the two right-hand toolbar
// buttons; disabled entirely when the editor has no project context.

extension SectionEditorView {

    enum MediaKind {
        case image, video

        var contentTypes: [UTType] {
            switch self {
            case .image: return [.png, .jpeg, .gif, .webP, .heic, .svg]
            case .video: return [.movie, .video, .quickTimeMovie, .mpeg4Movie]
            }
        }

        /// Fallback when the file extension doesn't map to a known UTType.
        var fallbackMimeType: String {
            self == .image ? "image/png" : "video/mp4"
        }

        /// Markdown / HTML written into the note once the upload resolves.
        func snippet(url: String, sourceName: String) -> String {
            switch self {
            case .image: return "![\(sourceName)](\(url))"
            case .video: return "<video src=\"\(url)\" controls width=\"100%\"></video>"
            }
        }
    }

    /// Max upload size, matched to the server's blog-media limit.
    private static var maxMediaBytes: Int { 50 * 1024 * 1024 }

    func pickMedia(kind: MediaKind) {
        guard projectId != nil else { return }
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = kind.contentTypes
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
        if data.count > Self.maxMediaBytes {
            await MainActor.run { uploadError = "File exceeds 50 MB" }
            return
        }
        let ext = url.pathExtension.lowercased()
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? kind.fallbackMimeType
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
                controller.insertBlock(
                    kind.snippet(url: uploaded.url,
                                 sourceName: url.deletingPathExtension().lastPathComponent)
                )
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
