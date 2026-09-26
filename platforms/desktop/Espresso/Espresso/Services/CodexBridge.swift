import Foundation

/// Owns one bundled child. It never reads Codex's credential files or inherits
/// the terminal's environment/config. A new Matcha bearer requires a new child.
actor CodexBridge {
    private var process: Process?
    private var stopping: Process?
    private var input: FileHandle?
    private var reader: Task<Void, Never>?
    private var errors: Task<Void, Never>?
    private var framer = CodexLineFramer()
    private var generation = UUID()
    private var pending: [String: CheckedContinuation<CodexJSON, Error>] = [:]
    private var timeouts: [String: Task<Void, Never>] = [:]
    private var sink: AsyncStream<CodexJSON>.Continuation?

    func start(userID: String, token: String? = nil) async throws -> AsyncStream<CodexJSON> {
        let previous = process ?? stopping
        stop()
        let launching = generation
        // Do not overlap children sharing a credential home during restart.
        for _ in 0..<25 where previous?.isRunning == true {
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        try Task.checkCancellation()
        guard generation == launching else { throw CancellationError() }
        guard previous?.isRunning != true else { throw CodexFailure(message: "The previous Codex process has not stopped yet.") }
        guard UUID(uuidString: userID) != nil else { throw CodexFailure(message: "Sign in to Matcha first.") }
        let root = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers")
        let executable = root.appendingPathComponent("codex")
        guard FileManager.default.isExecutableFile(atPath: executable.path),
              FileManager.default.isExecutableFile(atPath: root.appendingPathComponent("codex-code-mode-host").path) else {
            throw CodexFailure(message: "This Espresso build does not include the Codex runtime.")
        }
        let home = URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support/EspressoCodex/\(userID)")
        let work = home.appendingPathComponent("work")
        try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let child = Process()
        child.executableURL = executable
        child.arguments = ["app-server", "-c", "cli_auth_credentials_store=\"file\"", "-c", "check_for_update_on_startup=false", "-c", "features.apps=false", "-c", "features.shell_tool=false", "-c", "features.shell_snapshot=false"]
        child.currentDirectoryURL = work
        child.environment = ["HOME": NSHomeDirectory(), "CODEX_HOME": home.path,
                             "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": NSTemporaryDirectory(), "RUST_LOG": "off"]
        if let token { child.environment?["MATCHA_MCP_TOKEN"] = token }
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        child.standardInput = stdin; child.standardOutput = stdout; child.standardError = stderr
        let current = generation
        let stream = AsyncStream<CodexJSON>(bufferingPolicy: .bufferingOldest(256)) { sink = $0 }
        process = child; input = stdin.fileHandleForWriting
        do { try child.run() } catch { stop(); throw CodexFailure(message: "The bundled Codex process could not start.") }
        // A single ordered reader: independent readabilityHandler tasks can
        // reorder chunks or leave a pipe undrained during an actor suspension.
        reader = Task.detached { [weak self] in
            while !Task.isCancelled {
                let bytes = stdout.fileHandleForReading.availableData
                if bytes.isEmpty { break }
                await self?.receive(bytes, generation: current)
            }
            await self?.ended(generation: current)
        }
        errors = Task.detached {
            // Drain without persisting stderr: upstream diagnostics can contain
            // URLs, account details, and tool arguments.
            while !Task.isCancelled {
                if stderr.fileHandleForReading.availableData.isEmpty { break }
            }
        }
        do {
            _ = try await request("initialize", .object(["clientInfo": .object([
                "name": .string("espresso"), "title": .string("Espresso"), "version": .string("1.0")])]))
            try send(.object(["method": .string("initialized")]))
        } catch { stop(); throw error }
        return stream
    }

    func request(_ method: String, _ params: CodexJSON = .object([:]), timeout: UInt64 = 30) async throws -> CodexJSON {
        try Task.checkCancellation()
        let id = UUID().uuidString
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                guard process?.isRunning == true else {
                    continuation.resume(throwing: CodexFailure(message: "Codex is not running.")); return
                }
                pending[id] = continuation
                timeouts[id] = Task { [weak self] in
                    do { try await Task.sleep(nanoseconds: timeout * 1_000_000_000) } catch { return }
                    await self?.fail(id, error: CodexFailure(message: "Codex did not respond in time. Try again."))
                }
                do { try send(.object(["id": .string(id), "method": .string(method), "params": params])) }
                catch { fail(id, error: error) }
            }
        } onCancel: { Task { await self.fail(id, error: CancellationError()) } }
    }

    private func send(_ value: CodexJSON) throws {
        guard let input else { throw CodexFailure(message: "Codex is not running.") }
        var data = try JSONEncoder().encode(value)
        guard data.count <= CodexLineFramer.maximumBytes else { throw CodexFailure(message: "This Codex request is too large.") }
        data.append(10)
        try input.write(contentsOf: data)
    }

    private func receive(_ data: Data, generation current: UUID) {
        guard generation == current else { return }
        do {
            for message in try framer.append(data) {
                if message["method"].string != nil {
                    if message["id"] != .null {
                        // Research requires no commands, edits, elicitation, or
                        // credential forwarding. Never approve server requests.
                        try send(.object(["id": message["id"], "error": .object([
                            "code": .number(-32601), "message": .string("Espresso does not support this request.")])]))
                    } else if case .dropped = sink?.yield(message) {
                        throw CodexFailure(message: "Codex progress overflowed. Check the card before retrying.")
                    }
                } else if let id = message["id"].string, let continuation = pending.removeValue(forKey: id) {
                    timeouts.removeValue(forKey: id)?.cancel()
                    if message["error"] != .null {
                        // Don't surface arbitrary upstream payloads containing secrets.
                        continuation.resume(throwing: CodexFailure(message: "Codex rejected the request. Check your ChatGPT sign-in and usage limits."))
                    } else { continuation.resume(returning: message["result"]) }
                }
            }
        } catch { stop(error: CodexFailure(message: "Codex sent invalid progress. Check the card before retrying.")) }
    }

    private func fail(_ id: String, error: Error) {
        timeouts.removeValue(forKey: id)?.cancel()
        pending.removeValue(forKey: id)?.resume(throwing: error)
    }

    private func ended(generation current: UUID) {
        guard generation == current else { return }
        stop(error: CodexFailure(message: "Codex stopped unexpectedly. Check the card before retrying."))
    }

    func stop(error: CodexFailure? = nil) {
        generation = UUID()
        if let error { sink?.yield(.object(["method": .string("espresso/error"), "params": .string(error.message)])) }
        sink?.finish(); sink = nil
        let failure = error ?? CodexFailure(message: "Codex stopped.")
        for id in Array(pending.keys) { fail(id, error: failure) }
        try? input?.close(); input = nil
        if let child = process, child.isRunning {
            stopping = child
            child.terminate()
            DispatchQueue.global().asyncAfter(deadline: .now() + 1) {
                if child.isRunning { kill(child.processIdentifier, SIGKILL) }
            }
        }
        process = nil
        reader?.cancel(); reader = nil; errors?.cancel(); errors = nil
        framer = CodexLineFramer()
    }

    /// App termination must wait for the kill fallback; a timer in the parent
    /// cannot clean up a stuck child after the parent has already exited.
    func shutdown() async {
        stop()
        let child = stopping
        for _ in 0..<30 where child?.isRunning == true {
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
        if let child, child.isRunning { kill(child.processIdentifier, SIGKILL) }
        stopping = nil
    }
}
