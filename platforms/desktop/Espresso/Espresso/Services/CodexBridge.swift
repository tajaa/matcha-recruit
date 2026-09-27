import Foundation

/// Owns one bundled child. It never reads Codex's credential files or inherits
/// the terminal's environment/config. A new Matcha bearer requires a new child.
actor CodexBridge {
    /// The only notifications the coordinator acts on. Everything else (reasoning
    /// and command-output deltas, token counts, …) is dropped here, so the event
    /// stream carries a bounded trickle and never needs a lossy buffer.
    static let forwardedMethods: Set<String> = [
        "account/login/completed", "item/started", "item/completed", "turn/completed", CodexDeltaCoalescer.method,
    ]
    /// Streamed answer text arrives a few characters per message; the UI gets
    /// it batched at most this often.
    static let deltaInterval: UInt64 = 100_000_000

    private var process: Process?
    private var launchedUser: String?
    private var launchedWithToken = false
    private var stopping: Process?
    private var input: FileHandle?
    private var reader: Task<Void, Never>?
    private var framer = CodexLineFramer()
    private var generation = UUID()
    private var pending: [String: CheckedContinuation<CodexJSON, Error>] = [:]
    private var timeouts: [String: Task<Void, Never>] = [:]
    private var sink: AsyncStream<CodexJSON>.Continuation?
    private var deltas = CodexDeltaCoalescer()
    private var deltaFlush: Task<Void, Never>?

    /// A running, token-less child for this user — reused for account checks
    /// instead of paying another process launch and model-catalog refresh.
    func isServing(userID: String) -> Bool {
        process?.isRunning == true && launchedUser == userID && !launchedWithToken
    }

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
        // Unbounded is safe: only `forwardedMethods` reach it and agent text
        // is coalesced, so volume is a handful of events per second at most.
        let stream = AsyncStream<CodexJSON>(bufferingPolicy: .unbounded) { sink = $0 }
        process = child; input = stdin.fileHandleForWriting
        launchedUser = userID; launchedWithToken = token != nil
        do { try child.run() } catch { stop(); throw CodexFailure(message: "The bundled Codex process could not start.") }
        // Blocking pipe reads get their own threads, never the Swift
        // concurrency pool. One ordered stream per pipe: independent
        // readabilityHandler callbacks can reorder chunks.
        let chunks = Self.drain(stdout.fileHandleForReading)
        // Drain without persisting stderr: upstream diagnostics can contain
        // URLs, account details, and tool arguments.
        _ = Self.drain(stderr.fileHandleForReading, keep: false)
        reader = Task.detached { [weak self] in
            for await bytes in chunks {
                await self?.receive(bytes, generation: current)
            }
            await self?.ended(generation: current)
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

    /// Reads `handle` to EOF on a dedicated thread, discarding the bytes unless
    /// `keep`. The child's exit (or termination in `stop`) closes the pipe and
    /// ends both the thread and the stream.
    private nonisolated static func drain(_ handle: FileHandle, keep: Bool = true) -> AsyncStream<Data> {
        let (chunks, sink) = AsyncStream<Data>.makeStream(bufferingPolicy: .unbounded)
        let thread = Thread {
            while true {
                let bytes = handle.availableData
                if bytes.isEmpty { break }
                if keep { sink.yield(bytes) }
            }
            sink.finish()
        }
        thread.name = "espresso.codex.pipe"
        thread.start()
        return chunks
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
                    } else if let method = message["method"].string, Self.forwardedMethods.contains(method) {
                        if method == CodexDeltaCoalescer.method { bufferDelta(message["params"], generation: current) }
                        else {
                            // Text streamed before an item completes must reach
                            // the UI before that item's completion does.
                            flushDeltas()
                            sink?.yield(message)
                        }
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

    private func bufferDelta(_ params: CodexJSON, generation current: UUID) {
        if let previous = deltas.append(params) { sink?.yield(previous) }
        guard deltaFlush == nil else { return }
        deltaFlush = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: Self.deltaInterval) } catch { return }
            await self?.flushDeltas(generation: current)
        }
    }

    private func flushDeltas(generation current: UUID? = nil) {
        if let current, current != generation { return }
        deltaFlush?.cancel(); deltaFlush = nil
        if let batch = deltas.take() { sink?.yield(batch) }
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
        process = nil; launchedUser = nil; launchedWithToken = false
        reader?.cancel(); reader = nil
        deltaFlush?.cancel(); deltaFlush = nil; deltas = CodexDeltaCoalescer()
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
