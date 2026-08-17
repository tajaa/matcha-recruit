import Foundation

final class PreviewService {
    static let shared = PreviewService()
    private init() {}

    func render(
        siteId: String,
        title: String?,
        slug: String?,
        blocks: [CappeBlock],
        theme: [String: JSONValue]?,
        meta: [String: JSONValue]?,
        editable: Bool
    ) async throws -> String {
        let body = CappePagePreviewRequest(
            title: title,
            slug: slug,
            content: ["blocks": .array(blocks.map { .object($0.fields) })],
            theme_config: theme,
            meta_config: meta,
            editable: editable
        )
        return try await APIClient.shared.requestHTML(
            method: "POST", path: "/sites/\(siteId)/preview", body: body
        )
    }
}
