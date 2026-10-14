import Foundation

struct PendingChannelAttachment: Identifiable, Hashable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String
    var size: Int { data.count }
    var isImage: Bool { mimeType.hasPrefix("image/") }
}

/// What a composer accepts. A channel takes nearly any file; a conversation
/// with Espresso takes what it can read, under the server's limits
/// (server: agent_runtime/inputs.py). The server enforces the same rules.
struct AttachmentRules: Equatable {
    let maxFiles: Int
    let maxFileBytes: Int
    /// All the message's files together; nil for no total limit.
    let maxTotalBytes: Int?
    /// Extensions allowed; nil allows anything not in `blocked`.
    let allowed: Set<String>?
    let blocked: Set<String>

    static let channel = AttachmentRules(
        maxFiles: 10, maxFileBytes: 50 * 1024 * 1024, maxTotalBytes: nil, allowed: nil,
        // Block only executable / installer types; everything else (docs,
        // markdown, code, images, video, audio, archives, …) is allowed.
        blocked: [
            "exe", "msi", "bat", "cmd", "com", "scr", "vbs", "ps1",
            "app", "dmg", "pkg", "deb", "rpm", "apk", "jar", "bin",
            "command", "scpt", "action", "workflow",
        ]
    )

    /// HEIC is converted to JPEG before upload (`convertingHEIC`).
    static let espresso = AttachmentRules(
        maxFiles: 5, maxFileBytes: 10 * 1024 * 1024, maxTotalBytes: 25 * 1024 * 1024,
        allowed: ["pdf", "docx", "doc", "txt", "md", "csv", "json", "png", "jpg", "jpeg", "webp", "heic", "heif"],
        blocked: []
    )

    private static func megabytes(_ bytes: Int) -> String { "\(bytes / (1024 * 1024)) MB" }

    /// Why this file can't join the message, or nil when it can.
    func refusal(filename: String, size: Int, pending: [PendingChannelAttachment]) -> String? {
        let ext = (filename as NSString).pathExtension.lowercased()
        if blocked.contains(ext) { return "File type .\(ext) isn't allowed" }
        if let allowed, !allowed.contains(ext) {
            return "Espresso reads PDF, Word, text, Markdown, CSV and JSON files, and images"
        }
        if pending.count >= maxFiles {
            return allowed != nil
                ? "Espresso takes up to \(maxFiles) files at a time"
                : "Max \(maxFiles) attachments per message"
        }
        if size > maxFileBytes { return "\(filename) is too large (max \(Self.megabytes(maxFileBytes)))" }
        if let maxTotalBytes, pending.reduce(0, { $0 + $1.size }) + size > maxTotalBytes {
            return "Those files are over \(Self.megabytes(maxTotalBytes)) together"
        }
        return nil
    }
}
