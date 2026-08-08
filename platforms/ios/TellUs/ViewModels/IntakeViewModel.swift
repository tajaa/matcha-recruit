import Foundation
import Observation
import PhotosUI
import SwiftUI
import UIKit

/// FileRepresentation-backed Transferable for video PhotosPickerItems — lets
/// addPhotoItems stream large videos from disk instead of loading the whole
/// thing into memory as Data (the Data path stays for photos).
struct MovieFile: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { received in
            let dest = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString + "_" + received.file.lastPathComponent)
            try FileManager.default.copyItem(at: received.file, to: dest)
            return Self(url: dest)
        }
    }
}

/// What produced a PendingMedia — retained so a failed upload can be retried
/// without asking the user to re-pick the file.
enum PendingUploadSource {
    case bytes(Data, mimeType: String, filename: String)
    case file(URL, mimeType: String, filename: String)
}

struct PendingMedia: Identifiable {
    enum State: Equatable {
        case uploading
        case done(SubmittedMediaBox)
        case failed(String)
    }
    let id = UUID().uuidString
    var thumbnail: UIImage?
    var state: State
    let mediaType: MediaType
    let source: PendingUploadSource
}

/// SubmittedMedia isn't Equatable; box it so PendingMedia.State can be.
struct SubmittedMediaBox: Equatable {
    let value: SubmittedMedia
    static func == (lhs: SubmittedMediaBox, rhs: SubmittedMediaBox) -> Bool {
        lhs.value.storage_path == rhs.value.storage_path
    }
}

@MainActor
@Observable
final class IntakeViewModel {
    let token: String
    var config: IntakeConfig?
    var loadError: String?

    var category = ""
    var sentiment: Sentiment = .neutral
    var title = ""
    var description = ""
    var rating = 0
    var postAsReview = true
    var answers: [String: String] = [:]
    var mediaItems: [PendingMedia] = []

    var isSubmitting = false
    var submitError: String?
    var result: FeedbackSubmitResponse?

    init(token: String) { self.token = token }

    func loadConfig() async {
        do {
            let cfg = try await IntakeService.shared.config(token: token)
            config = cfg
            category = cfg.categories.first ?? ""
            loadError = nil
        } catch {
            if error.isCancellation { return }
            loadError = error.localizedDescription
        }
    }

    func addPhotoItems(_ items: [PhotosPickerItem]) {
        for item in items {
            let mediaType: MediaType = (item.supportedContentTypes.first?.conforms(to: .movie) ?? false) ? .video : .photo
            switch mediaType {
            case .photo:
                addPhotoBytes(item)
            case .video:
                addVideoFile(item)
            }
        }
    }

    private func addPhotoBytes(_ item: PhotosPickerItem) {
        let utType = item.supportedContentTypes.first ?? .jpeg
        let mime = utType.preferredMIMEType ?? "application/octet-stream"
        let pendingId = UUID().uuidString
        let filename = "upload_\(pendingId)"
        mediaItems.append(PendingMedia(
            id: pendingId, thumbnail: nil, state: .uploading, mediaType: .photo,
            source: .bytes(Data(), mimeType: mime, filename: filename)  // placeholder until bytes load; replaced below
        ))
        Task { [weak self] in
            guard let self else { return }
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else {
                    self.updateMedia(pendingId) { $0.state = .failed("Couldn't load file") }
                    return
                }
                self.updateMedia(pendingId) { $0.thumbnail = MediaUploadService.photoThumbnail(from: data) }
                self.setSource(pendingId, .bytes(data, mimeType: mime, filename: filename))
                await self.uploadBytes(id: pendingId, data: data, mimeType: mime, filename: filename)
            } catch {
                if error.isCancellation { return }
                self.updateMedia(pendingId) { $0.state = .failed(error.localizedDescription) }
            }
        }
    }

    private func addVideoFile(_ item: PhotosPickerItem) {
        let utType = item.supportedContentTypes.first ?? .movie
        let mime = utType.preferredMIMEType ?? "video/mp4"
        let pendingId = UUID().uuidString
        let filename = "upload_\(pendingId).mov"
        mediaItems.append(PendingMedia(
            id: pendingId, thumbnail: nil, state: .uploading, mediaType: .video,
            source: .file(FileManager.default.temporaryDirectory, mimeType: mime, filename: filename)  // placeholder, replaced once the real file lands
        ))
        Task { [weak self] in
            guard let self else { return }
            do {
                guard let movie = try await item.loadTransferable(type: MovieFile.self) else {
                    self.updateMedia(pendingId) { $0.state = .failed("Couldn't load file") }
                    return
                }
                self.updateMedia(pendingId) { $0.thumbnail = MediaUploadService.videoThumbnail(url: movie.url) }
                self.setSource(pendingId, .file(movie.url, mimeType: mime, filename: filename))
                await self.uploadFile(id: pendingId, url: movie.url, mimeType: mime, filename: filename)
            } catch {
                if error.isCancellation { return }
                self.updateMedia(pendingId) { $0.state = .failed(error.localizedDescription) }
            }
        }
    }

    func addCameraImage(_ image: UIImage) {
        guard let jpeg = image.jpegData(compressionQuality: 0.85) else { return }
        let pendingId = UUID().uuidString
        mediaItems.append(PendingMedia(
            id: pendingId, thumbnail: image, state: .uploading, mediaType: .photo,
            source: .bytes(jpeg, mimeType: "image/jpeg", filename: "camera.jpg")
        ))
        Task { [weak self] in
            await self?.uploadBytes(id: pendingId, data: jpeg, mimeType: "image/jpeg", filename: "camera.jpg")
        }
    }

    /// Re-runs the upload for a failed item using its retained source —
    /// no re-pick required.
    func retryMedia(id: String) {
        guard let item = mediaItems.first(where: { $0.id == id }) else { return }
        updateMedia(id) { $0.state = .uploading }
        switch item.source {
        case .bytes(let data, let mimeType, let filename):
            Task { [weak self] in await self?.uploadBytes(id: id, data: data, mimeType: mimeType, filename: filename) }
        case .file(let url, let mimeType, let filename):
            Task { [weak self] in await self?.uploadFile(id: id, url: url, mimeType: mimeType, filename: filename) }
        }
    }

    private func uploadBytes(id: String, data: Data, mimeType: String, filename: String) async {
        do {
            let prepared = try MediaUploadService.prepare(data: data, mimeType: mimeType, filename: filename, mediaType: .photo)
            let submitted = try await MediaUploadService.shared.upload(token: token, prepared: prepared)
            updateMedia(id) { $0.state = .done(SubmittedMediaBox(value: submitted)) }
        } catch {
            if error.isCancellation { return }
            updateMedia(id) { $0.state = .failed(error.localizedDescription) }
        }
    }

    private func uploadFile(id: String, url: URL, mimeType: String, filename: String) async {
        defer { try? FileManager.default.removeItem(at: url) }
        do {
            let prepared = try MediaUploadService.prepareFile(url: url, mimeType: mimeType, filename: filename)
            let submitted = try await MediaUploadService.shared.upload(token: token, file: prepared)
            updateMedia(id) { $0.state = .done(SubmittedMediaBox(value: submitted)) }
        } catch {
            if error.isCancellation { return }
            updateMedia(id) { $0.state = .failed(error.localizedDescription) }
        }
    }

    private func setSource(_ id: String, _ source: PendingUploadSource) {
        guard let idx = mediaItems.firstIndex(where: { $0.id == id }) else { return }
        let old = mediaItems[idx]
        mediaItems[idx] = PendingMedia(id: old.id, thumbnail: old.thumbnail, state: old.state, mediaType: old.mediaType, source: source)
    }

    private func updateMedia(_ id: String, _ mutate: (inout PendingMedia) -> Void) {
        guard let idx = mediaItems.firstIndex(where: { $0.id == id }) else { return }
        mutate(&mediaItems[idx])
    }

    func removeMedia(id: String) {
        mediaItems.removeAll { $0.id == id }
    }

    var canSubmit: Bool {
        !description.isEmpty && (!postAsReview || rating > 0) && !isSubmitting
    }

    /// Trims + drops empty answers. Extracted so Tests/IntakeSubmissionEncodingTests.swift
    /// exercises the real submit-time transform instead of a re-implementation.
    /// nonisolated (pure function, no actor state) so the sync test can call
    /// it without hopping onto MainActor.
    nonisolated static func trimmedAnswers(_ answers: [String: String]) -> [IntakeAnswerOut] {
        answers
            .map { ($0.key, $0.value.trimmingCharacters(in: .whitespacesAndNewlines)) }
            .filter { !$0.1.isEmpty }
            .sorted { $0.0 < $1.0 }
            .map { IntakeAnswerOut(prompt_id: $0.0, answer: $0.1) }
    }

    func submit() async {
        guard canSubmit else {
            if postAsReview && rating == 0 {
                submitError = "Please pick a star rating for your public review."
            }
            return
        }
        isSubmitting = true; defer { isSubmitting = false }
        submitError = nil
        let mediaKeys = mediaItems.compactMap { item -> SubmittedMedia? in
            if case .done(let box) = item.state { return box.value }
            return nil
        }
        let body = IntakeSubmission(
            category: category, sentiment: sentiment.rawValue,
            title: title.isEmpty ? nil : title,
            description: description,
            reporter_contact: nil,
            rating: rating > 0 ? rating : nil,
            post_as_review: postAsReview,
            media_keys: mediaKeys,
            website: "",
            answers: Self.trimmedAnswers(answers)
        )
        do {
            result = try await IntakeService.shared.submit(token: token, body)
        } catch {
            if error.isCancellation { return }
            submitError = error.localizedDescription
        }
    }
}
