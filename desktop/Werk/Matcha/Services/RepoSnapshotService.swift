import Foundation

/// One file in an element's uploaded code snapshot.
struct RepoFilePayload: Encodable {
    let path: String
    let content: String
    let hash: String?
}

/// Reads the connector's local clone (via FileManager — sandbox-safe, no git) and
/// groups text files per element by glob, ready to PUT as each element's repo
/// snapshot. The snapshot is what grounds a Prop's repo chat. Caller must hold
/// security-scoped access to `root`; run off the main actor (blocking IO).
enum RepoSnapshotService {
    static let maxFileBytes = 40_000
    static let maxFilesPerElement = 600
    static let maxBytesPerElement = 5_000_000

    static let excludedDirs: Set<String> = [
        ".git", "node_modules", "dist", "build", ".build", "Pods", "DerivedData",
        ".venv", "venv", "__pycache__", ".next", "target", "vendor",
        ".pytest_cache", "coverage", ".idea", ".turbo", ".cache", ".gradle",
    ]
    static let excludedNames: Set<String> = [
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Podfile.lock",
        "Cargo.lock", "poetry.lock", "composer.lock", "Gemfile.lock",
    ]

    struct ElementGlobs {
        let id: String
        let globs: [String]
    }

    /// Walk `root` once; return [elementId: [files]] for elements with globs.
    static func collect(root: URL, elements: [ElementGlobs]) -> [String: [RepoFilePayload]] {
        let targets = elements.filter { !$0.globs.isEmpty }
        guard !targets.isEmpty else { return [:] }

        var result: [String: [RepoFilePayload]] = [:]
        var bytesPerElement: [String: Int] = [:]
        let fm = FileManager.default
        let rootPath = root.path.hasSuffix("/") ? root.path : root.path + "/"

        guard let en = fm.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey, .isDirectoryKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { return result }

        for case let url as URL in en {
            let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .isDirectoryKey, .fileSizeKey])
            if values?.isDirectory == true {
                if excludedDirs.contains(url.lastPathComponent) { en.skipDescendants() }
                continue
            }
            guard values?.isRegularFile == true else { continue }
            if excludedNames.contains(url.lastPathComponent) { continue }
            if let sz = values?.fileSize, sz > maxFileBytes { continue }

            guard url.path.hasPrefix(rootPath) else { continue }
            let rel = String(url.path.dropFirst(rootPath.count))
            if rel.isEmpty { continue }

            let owners = targets.filter { eg in eg.globs.contains { GitService.pathMatchesGlob(rel, $0) } }
            if owners.isEmpty { continue }

            // Text only: must be valid UTF-8 with no NUL byte.
            guard let data = try? Data(contentsOf: url), !data.isEmpty,
                  !data.contains(0), let text = String(data: data, encoding: .utf8) else { continue }
            let size = data.count

            for eg in owners {
                let used = bytesPerElement[eg.id] ?? 0
                let count = result[eg.id]?.count ?? 0
                if count >= maxFilesPerElement || used + size > maxBytesPerElement { continue }
                result[eg.id, default: []].append(RepoFilePayload(path: rel, content: text, hash: nil))
                bytesPerElement[eg.id] = used + size
            }
        }
        return result
    }
}
