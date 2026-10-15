import Foundation
import Observation

/// Email ▸ Drafts: the person's Gmail drafts, the one open, and its edits.
/// Saving writes the draft back to Gmail (it stays a draft there too);
/// Send sends exactly what is saved, after saving any edits first.
@Observable @MainActor
final class EmailDraftsViewModel {
    static let shared = EmailDraftsViewModel()

    var drafts: [EmailDraftSummary] = []
    var loaded = false
    var loading = false

    var selectedId: String?
    /// The draft as Gmail has it.
    private(set) var saved: EmailDraft?
    var to = ""
    var subject = ""
    var body = ""

    var busy = false
    var errorMessage: String?
    /// A short confirmation ("Saved", "Sent").
    var notice: String?

    private let service = EmailService.shared

    var isDirty: Bool {
        guard let saved else { return false }
        return saved.to != to || saved.subject != subject || saved.body != body
    }

    /// Bracketed parts a drafted message left for the person ("[Your name]").
    var placeholders: [String] { Self.placeholders(in: subject + "\n" + body) }

    // MARK: Loading

    func load() async {
        loading = true
        defer { loading = false }
        do {
            drafts = try await service.drafts()
            loaded = true
            errorMessage = nil
        } catch is CancellationError {
        } catch { report(error) }
    }

    func select(_ id: String?) async {
        if isDirty { _ = await save() }
        selectedId = id
        saved = nil
        notice = nil
        guard let id else { to = ""; subject = ""; body = ""; return }
        do {
            let draft = try await service.draft(id: id)
            guard selectedId == id else { return }
            apply(draft)
        } catch is CancellationError {
        } catch {
            if case APIError.httpError(404, _) = error {
                drafts.removeAll { $0.id == id }
                selectedId = nil
                errorMessage = "That draft was sent or deleted."
            } else {
                report(error)
            }
        }
    }

    private func apply(_ draft: EmailDraft) {
        saved = draft
        to = draft.to
        subject = draft.subject
        body = draft.body
        if let i = drafts.firstIndex(where: { $0.id == draft.id }) {
            drafts[i].to = draft.to
            drafts[i].subject = draft.subject
            drafts[i].snippet = String(draft.body.prefix(120))
        }
    }

    // MARK: Actions

    @discardableResult
    func save() async -> Bool {
        guard let id = selectedId, isDirty else { return true }
        busy = true
        defer { busy = false }
        do {
            apply(try await service.saveDraft(id: id, to: to, subject: subject, body: body))
            notice = "Saved"
            errorMessage = nil
            return true
        } catch {
            report(error)
            return false
        }
    }

    @discardableResult
    func send() async -> Bool {
        guard let id = selectedId else { return false }
        guard await save() else { return false }
        busy = true
        defer { busy = false }
        do {
            try await service.sendDraft(id: id)
            drafts.removeAll { $0.id == id }
            selectedId = nil
            saved = nil
            to = ""; subject = ""; body = ""
            notice = "Sent"
            errorMessage = nil
            return true
        } catch {
            report(error)
            return false
        }
    }

    func delete() async {
        guard let id = selectedId else { return }
        busy = true
        defer { busy = false }
        do {
            try await service.deleteDraft(id: id)
            drafts.removeAll { $0.id == id }
            selectedId = nil
            saved = nil
            to = ""; subject = ""; body = ""
            notice = "Deleted"
        } catch { report(error) }
    }

    func report(_ error: Error) {
        errorMessage = (error as? APIError).map { AssistantText.message(for: $0) } ?? error.localizedDescription
    }

    /// The person signed out, or another account signed in.
    func reset() {
        drafts = []; loaded = false; selectedId = nil; saved = nil
        to = ""; subject = ""; body = ""; errorMessage = nil; notice = nil
    }

    // MARK: Pure helpers (tested)

    /// Every `[…]` the text still holds, once each, in order.
    nonisolated static func placeholders(in text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"\[[^\[\]\n]{2,80}\]"#) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        var out: [String] = []
        for match in regex.matches(in: text, range: range) {
            guard let r = Range(match.range, in: text) else { continue }
            let found = String(text[r])
            if !out.contains(found) { out.append(found) }
        }
        return out
    }
}
