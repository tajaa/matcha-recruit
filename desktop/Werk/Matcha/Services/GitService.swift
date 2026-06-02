import Foundation

/// Commit payload posted to the backend `/commit-scan` endpoint. snake_case
/// keys match the API contract.
struct GitCommitPayload: Encodable {
    let sha: String
    let short_sha: String
    let message: String
    let changed_files: [String]
    let diff: String
}

enum GitError: LocalizedError {
    case gitNotFound
    case notARepo(String)
    case commandFailed(String)
    case timedOut

    var errorDescription: String? {
        switch self {
        case .gitNotFound:
            return "Couldn't find git on this machine (looked in /opt/homebrew/bin, /usr/bin, /usr/local/bin)."
        case .notARepo(let p):
            return "That folder isn't a git repository: \(p)"
        case .commandFailed(let m):
            return "git failed: \(m)"
        case .timedOut:
            return "git command timed out."
        }
    }
}

/// Persists which local clone backs each project (a security-scoped bookmark,
/// required to read a user-picked folder across launches in the sandbox) plus
/// the last-scanned commit per (project, branch). All machine-specific — never
/// sent to the server.
enum RepoConnectionStore {
    private static func bookmarkKey(_ projectId: String) -> String { "werk.repo.bookmark.\(projectId)" }
    private static func shaKey(_ projectId: String, _ branch: String) -> String { "werk.repo.lastSha.\(projectId).\(branch)" }

    static func setRepo(projectId: String, url: URL) throws {
        let data = try url.bookmarkData(
            options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil
        )
        UserDefaults.standard.set(data, forKey: bookmarkKey(projectId))
        // A (re)connect points at a different clone — drop stale per-branch
        // watermarks so the new repo scans recent history fresh rather than
        // skipping commits behind an old repo's SHA.
        clearWatermarks(projectId: projectId)
    }

    static func clearRepo(projectId: String) {
        UserDefaults.standard.removeObject(forKey: bookmarkKey(projectId))
        clearWatermarks(projectId: projectId)
    }

    /// Remove every `werk.repo.lastSha.<projectId>.<branch>` key (UserDefaults
    /// has no prefix-delete, so enumerate).
    static func clearWatermarks(projectId: String) {
        let prefix = "werk.repo.lastSha.\(projectId)."
        let defaults = UserDefaults.standard
        for key in defaults.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
            defaults.removeObject(forKey: key)
        }
    }

    /// Resolves the bookmark to a URL. The caller MUST bracket use with
    /// `startAccessingSecurityScopedResource()` / `stopAccessingSecurityScopedResource()`.
    static func repoURL(projectId: String) -> URL? {
        guard let data = UserDefaults.standard.data(forKey: bookmarkKey(projectId)) else { return nil }
        var stale = false
        guard let url = try? URL(
            resolvingBookmarkData: data, options: .withSecurityScope,
            relativeTo: nil, bookmarkDataIsStale: &stale
        ) else { return nil }
        if stale, let fresh = try? url.bookmarkData(
            options: .withSecurityScope, includingResourceValuesForKeys: nil, relativeTo: nil
        ) {
            UserDefaults.standard.set(fresh, forKey: bookmarkKey(projectId))
        }
        return url
    }

    /// Display path for the connected repo (no security scope needed to read it).
    static func repoDisplayPath(projectId: String) -> String? {
        repoURL(projectId: projectId)?.path
    }

    static func lastSha(projectId: String, branch: String) -> String? {
        UserDefaults.standard.string(forKey: shaKey(projectId, branch))
    }

    static func setLastSha(projectId: String, branch: String, sha: String) {
        UserDefaults.standard.set(sha, forKey: shaKey(projectId, branch))
    }
}

/// Sandbox-aware git shell-out. All calls are blocking — run them off the main
/// actor (e.g. inside `Task.detached`). The caller must already hold
/// security-scoped access to `root`.
enum GitService {
    private static let unitSep = "\u{1f}"  // US — between fields in a log record
    private static let recSep = "\u{1e}"   // RS — between log records
    static let maxFirstScan = 30           // never replay whole history on first scan
    private static let maxDiffChars = 60_000
    private static let maxDiffFiles = 25
    private static let commandTimeout: TimeInterval = 15

    static func resolveGitBinary() -> URL? {
        // Prefer a REAL git binary (Homebrew) over Apple's /usr/bin/git shim —
        // the shim re-execs Xcode's git via xcrun, which the App Sandbox tends
        // to block (can't read /Applications/Xcode.app). Real CLT/Xcode git
        // paths are tried last as fallbacks.
        for p in [
            "/opt/homebrew/bin/git",
            "/usr/local/bin/git",
            "/usr/bin/git",
            "/Library/Developer/CommandLineTools/usr/bin/git",
            "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
        ] where FileManager.default.isExecutableFile(atPath: p) {
            return URL(fileURLWithPath: p)
        }
        return nil
    }

    /// Run `git -C <root> <args>` and return stdout. Drains stdout/stderr on
    /// background threads so a large diff can't fill the pipe buffer and
    /// deadlock the child before we read it.
    @discardableResult
    static func run(_ args: [String], in root: URL) throws -> String {
        guard let git = resolveGitBinary() else { throw GitError.gitNotFound }
        let proc = Process()
        proc.executableURL = git
        proc.currentDirectoryURL = root
        proc.arguments = ["-C", root.path] + args
        var env = ProcessInfo.processInfo.environment
        env["GIT_TERMINAL_PROMPT"] = "0"   // never block on a credential prompt
        env["GIT_OPTIONAL_LOCKS"] = "0"
        proc.environment = env

        let outPipe = Pipe(); let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe

        final class Box { var data = Data() }
        let outBox = Box(); let errBox = Box()
        let group = DispatchGroup()
        let q = DispatchQueue(label: "git.read", attributes: .concurrent)
        group.enter(); q.async { outBox.data = outPipe.fileHandleForReading.readDataToEndOfFile(); group.leave() }
        group.enter(); q.async { errBox.data = errPipe.fileHandleForReading.readDataToEndOfFile(); group.leave() }

        do { try proc.run() } catch { throw GitError.commandFailed(error.localizedDescription) }

        // The reads complete when the child closes its pipe ends (i.e. on exit).
        // If the child hangs, the reads never return → wait times out → kill.
        if group.wait(timeout: .now() + commandTimeout) == .timedOut {
            proc.terminate()
            throw GitError.timedOut
        }
        proc.waitUntilExit()

        if proc.terminationStatus != 0 {
            let estr = String(data: errBox.data, encoding: .utf8) ?? ""
            throw GitError.commandFailed(estr.isEmpty ? "git exited \(proc.terminationStatus)" : estr.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return String(data: outBox.data, encoding: .utf8) ?? ""
    }

    static func isRepo(_ root: URL) -> Bool {
        (try? run(["rev-parse", "--is-inside-work-tree"], in: root))?
            .trimmingCharacters(in: .whitespacesAndNewlines) == "true"
    }

    /// Current branch name, or nil in detached-HEAD.
    static func currentBranch(_ root: URL) -> String? {
        let b = (try? run(["rev-parse", "--abbrev-ref", "HEAD"], in: root))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (b?.isEmpty == false && b != "HEAD") ? b : nil
    }

    static func headSha(_ root: URL) -> String? {
        (try? run(["rev-parse", "HEAD"], in: root))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Commits since `sha` (exclusive) up to HEAD, oldest-first. On first scan
    /// (`sha == nil`) returns at most `maxFirstScan` recent commits — never the
    /// whole history.
    static func newCommits(at root: URL, since sha: String?, limit: Int = maxFirstScan) throws -> [GitCommitPayload] {
        var args = ["log", "--no-merges", "--reverse",
                    "--format=%H\(unitSep)%h\(unitSep)%B\(recSep)"]
        if let sha, !sha.isEmpty {
            args.append("\(sha)..HEAD")
        } else {
            args.append(contentsOf: ["-n", String(limit)])
        }
        let raw = try run(args, in: root)

        var commits: [GitCommitPayload] = []
        for record in raw.components(separatedBy: recSep) {
            let rec = record.trimmingCharacters(in: .whitespacesAndNewlines)
            if rec.isEmpty { continue }
            let parts = rec.components(separatedBy: unitSep)
            guard parts.count >= 3 else { continue }
            let full = parts[0].trimmingCharacters(in: .whitespacesAndNewlines)
            let short = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
            let message = parts[2].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !full.isEmpty else { continue }
            let (files, diff) = changeSet(for: full, in: root)
            commits.append(GitCommitPayload(
                sha: full, short_sha: short, message: message,
                changed_files: files, diff: diff
            ))
        }
        return commits
    }

    /// Changed file paths (incl. binaries) + a bounded unified diff over the
    /// non-binary files only.
    private static func changeSet(for sha: String, in root: URL) -> ([String], String) {
        // numstat lines: "added\tdeleted\tpath"; binary files show "-\t-\tpath".
        let numstat = (try? run(["show", sha, "--numstat", "--format="], in: root)) ?? ""
        var files: [String] = []
        var textFiles: [String] = []
        for line in numstat.split(separator: "\n") {
            let cols = line.components(separatedBy: "\t")
            guard cols.count >= 3 else { continue }
            let path = cols[2].trimmingCharacters(in: .whitespaces)
            if path.isEmpty { continue }
            files.append(path)
            if cols[0] != "-" { textFiles.append(path) }  // "-" added-count ⇒ binary
        }

        var diff = ""
        if !textFiles.isEmpty {
            let capped = Array(textFiles.prefix(maxDiffFiles))
            let raw = (try? run(["show", sha, "--unified=3", "--format=", "--"] + capped, in: root)) ?? ""
            diff = String(raw.prefix(maxDiffChars))
        }
        return (files, diff)
    }

    // MARK: - Glob matching (mirrors server commit_scan_service.path_matches_glob)

    private static func normalizePath(_ s: String) -> String {
        var p = s.replacingOccurrences(of: "\\", with: "/")
        if p.hasPrefix("./") { p = String(p.dropFirst(2)) }
        while p.hasPrefix("/") { p = String(p.dropFirst()) }
        return p
    }

    private static func lastComponent(_ p: String) -> String {
        p.split(separator: "/").last.map(String.init) ?? p
    }

    private static func fnmatchC(_ pattern: String, _ string: String) -> Bool {
        // POSIX fnmatch, case-sensitive, '*' spans '/' (matches Python fnmatch).
        return fnmatch(pattern, string, 0) == 0
    }

    /// True if a repo-relative path matches a single glob. Supported:
    /// exact · `dir/**` (recursive) · `dir/*` (one level) · `**/*.ext` · `*.ext`
    /// (basename) · generic fnmatch fallback.
    static func pathMatchesGlob(_ path: String, _ glob: String) -> Bool {
        let p = normalizePath(path)
        let g = normalizePath(glob)
        if p.isEmpty || g.isEmpty { return false }

        if g.hasSuffix("/**") {
            let prefix = String(g.dropLast(2))          // keeps trailing slash "dir/"
            return p == String(prefix.dropLast()) || p.hasPrefix(prefix)
        }
        if g.hasSuffix("/") { return p.hasPrefix(g) }
        if g.hasSuffix("/*") {
            let prefix = String(g.dropLast(1))          // "dir/"
            guard p.hasPrefix(prefix) else { return false }
            return !p.dropFirst(prefix.count).contains("/")
        }
        if g.hasPrefix("**/") {
            let pat = String(g.dropFirst(3))
            return fnmatchC(pat, p) || fnmatchC(pat, lastComponent(p))
        }
        if !g.contains("/") {
            return fnmatchC(g, lastComponent(p))
        }
        if p == g { return true }
        return fnmatchC(g, p)
    }
}
