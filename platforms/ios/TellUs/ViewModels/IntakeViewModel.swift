import Foundation
import Observation
import PhotosUI
import SwiftUI
import UIKit

struct PendingMedia: Identifiable {
    enum State: Equatable {
        case uploading
        case done(SubmittedMediaBox)
        case failed(String)
    }
    let id = UUID().uuidString
    let thumbnail: UIImage?
    var state: State
    let mediaType: MediaType
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
            loadError = error.localizedDescription
        }
    }

    func addPhotoItems(_ items: [PhotosPickerItem]) {
        for item in items {
            let mediaType: MediaType = (item.supportedContentTypes.first?.conforms(to: .movie) ?? false) ? .video : .photo
            var pending = PendingMedia(thumbnail: nil, state: .uploading, mediaType: mediaType)
            mediaItems.append(pending)
            let pendingId = pending.id
            Task { [weak self] in
                guard let self else { return }
                do {
                    guard let data = try await item.loadTransferable(type: Data.self) else {
                        self.updateMedia(pendingId) { $0.state = .failed("Couldn't load file") }
                        return
                    }
                    let utType = item.supportedContentTypes.first ?? .jpeg
                    let mime = utType.preferredMIMEType ?? "application/octet-stream"
                    let filename = "upload_\(pendingId)"
                    try await self.upload(id: pendingId, data: data, mimeType: mime, filename: filename, mediaType: mediaType)
                } catch {
                    self.updateMedia(pendingId) { $0.state = .failed(error.localizedDescription) }
                }
            }
            _ = pending // silence unused-var warning; state mutated via updateMedia
        }
    }

    func addCameraImage(_ image: UIImage) {
        guard let jpeg = image.jpegData(compressionQuality: 0.85) else { return }
        let pending = PendingMedia(thumbnail: image, state: .uploading, mediaType: .photo)
        mediaItems.append(pending)
        let pendingId = pending.id
        Task { [weak self] in
            try? await self?.upload(id: pendingId, data: jpeg, mimeType: "image/jpeg", filename: "camera.jpg", mediaType: .photo)
        }
    }

    private func upload(id: String, data: Data, mimeType: String, filename: String, mediaType: MediaType) async throws {
        do {
            let prepared = try MediaUploadService.prepare(data: data, mimeType: mimeType, filename: filename, mediaType: mediaType)
            let submitted = try await MediaUploadService.shared.upload(token: token, prepared: prepared)
            updateMedia(id) { $0.state = .done(SubmittedMediaBox(value: submitted)) }
        } catch {
            updateMedia(id) { $0.state = .failed(error.localizedDescription) }
        }
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
        let answersOut = answers
            .map { ($0.key, $0.value.trimmingCharacters(in: .whitespacesAndNewlines)) }
            .filter { !$0.1.isEmpty }
            .map { IntakeAnswerOut(prompt_id: $0.0, answer: $0.1) }
        let body = IntakeSubmission(
            category: category, sentiment: sentiment.rawValue,
            title: title.isEmpty ? nil : title,
            description: description,
            reporter_contact: nil,
            rating: rating > 0 ? rating : nil,
            post_as_review: postAsReview,
            media_keys: mediaKeys,
            website: "",
            answers: answersOut
        )
        do {
            result = try await IntakeService.shared.submit(token: token, body)
        } catch {
            if error.isCancellation { return }
            submitError = error.localizedDescription
        }
    }
}
