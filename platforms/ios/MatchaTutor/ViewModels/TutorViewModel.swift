import Foundation
import Combine

enum TutorSessionState: Equatable {
    case idle
    case starting
    case connecting
    case connected
    case recording
    case completed
    case error(String)

    static func == (lhs: TutorSessionState, rhs: TutorSessionState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle),
             (.starting, .starting),
             (.connecting, .connecting),
             (.connected, .connected),
             (.recording, .recording),
             (.completed, .completed):
            return true
        case (.error(let lhsMsg), .error(let rhsMsg)):
            return lhsMsg == rhsMsg
        default:
            return false
        }
    }
}

@MainActor
final class TutorViewModel: ObservableObject {
    // Session state
    @Published private(set) var sessionState: TutorSessionState = .idle
    @Published private(set) var messages: [WSMessage] = []
    @Published private(set) var sessionTimeRemaining: Int?
    @Published private(set) var isIdleWarning = false

    // Configuration
    @Published var selectedMode: TutorMode = .interviewPrep
    @Published var selectedLanguage: TutorLanguage = .spanish
    @Published var selectedDuration: SessionDuration = .medium
    @Published var selectedRole: InterviewRole = .juniorEngineer

    // Internal state
    private var interviewId: String?
    private var maxSessionDurationSeconds: Int = Int(SessionProtection.defaultMaxSessionDurationSeconds)

    private let apiClient = APIClient.shared
    private let webSocketManager = WebSocketManager()
    private let audioRecorder = AudioRecorder()
    private let audioPlayer = AudioPlayer()

    // Timers
    private var sessionTimer: Timer?
    private var idleTimer: Timer?
    private var warningTimer: Timer?
    private var sessionStartTime: Date?
    private var lastActivityTime: Date = Date()

    var isRecording: Bool {
        sessionState == .recording
    }

    var isConnected: Bool {
        sessionState == .connected || sessionState == .recording
    }

    // MARK: - Initialization

    init() {
        setupDelegates()
    }

    private func setupDelegates() {
        webSocketManager.delegate = self
        audioRecorder.delegate = self
        audioPlayer.delegate = self
        audioRecorder.setSharedEngine(audioPlayer.sharedEngine)
        audioRecorder.setupInterruptionHandling()
    }

    // MARK: - Session Management

    func startSession() async {
        sessionState = .starting
        messages = []

        do {
            let response = try await apiClient.createTutorSession(
                mode: selectedMode,
                language: selectedMode == .languageTest ? selectedLanguage : nil,
                durationMinutes: selectedMode == .languageTest ? selectedDuration.rawValue : selectedDuration.rawValue,
                interviewRole: selectedMode == .interviewPrep ? selectedRole.rawValue : nil
            )

            interviewId = response.interviewId
            maxSessionDurationSeconds = response.maxSessionDurationSeconds

            // Connect to WebSocket
            sessionState = .connecting
            webSocketManager.connect(interviewId: response.interviewId)

        } catch let error as APIError {
            sessionState = .error(error.errorDescription ?? "Failed to start session")
        } catch {
            sessionState = .error(error.localizedDescription)
        }
    }

    func connect() {
        guard let interviewId = interviewId, sessionState == .idle else { return }
        sessionState = .connecting
        webSocketManager.connect(interviewId: interviewId)
    }

    func disconnect() {
        stopRecording()
        stopAllTimers()
        webSocketManager.disconnect()
        audioRecorder.removeTap()
        try? audioPlayer.stop()
        sessionState = .idle
    }

    func endSession() {
        disconnect()
        sessionState = .completed
    }

    func resetSession() {
        interviewId = nil
        messages = []
        sessionTimeRemaining = nil
        isIdleWarning = false
        sessionState = .idle
    }

    // MARK: - Recording

    func startRecording() async {
        guard sessionState == .connected else { return }

        let hasPermission = await audioRecorder.requestPermission()
        guard hasPermission else {
            sessionState = .error(AudioRecorderError.microphonePermissionDenied.errorDescription ?? "Microphone access denied")
            return
        }

        do {
            try audioRecorder.startRecording()
            sessionState = .recording
            resetIdleTimer()
        } catch {
            sessionState = .error(error.localizedDescription)
        }
    }

    func stopRecording() {
        guard sessionState == .recording else { return }
        audioRecorder.stopRecording()
        sessionState = .connected
    }

    func toggleRecording() async {
        if isRecording {
            stopRecording()
        } else {
            await startRecording()
        }
    }

    // MARK: - Timers

    private func startSessionTimer() {
        sessionStartTime = Date()

        sessionTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.updateSessionTimer()
            }
        }

        resetIdleTimer()
    }

    private func updateSessionTimer() {
        guard let startTime = sessionStartTime else { return }

        let elapsed = Date().timeIntervalSince(startTime)
        let remaining = max(0, maxSessionDurationSeconds - Int(elapsed))
        sessionTimeRemaining = remaining

        // Warn at 1 minute remaining
        if remaining == 60 {
            addSystemMessage("1 minute remaining - session will end soon")
        }

        // Auto-disconnect at max duration
        if remaining == 0 {
            addSystemMessage("Maximum session duration reached. Disconnecting.")
            endSession()
        }
    }

    func resetIdleTimer() {
        lastActivityTime = Date()
        isIdleWarning = false

        warningTimer?.invalidate()
        idleTimer?.invalidate()

        guard isConnected else { return }

        let warningTime = SessionProtection.idleTimeoutSeconds - SessionProtection.warningBeforeDisconnectSeconds

        warningTimer = Timer.scheduledTimer(withTimeInterval: warningTime, repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.showIdleWarning()
            }
        }

        idleTimer = Timer.scheduledTimer(withTimeInterval: SessionProtection.idleTimeoutSeconds, repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.handleIdleTimeout()
            }
        }
    }

    private func showIdleWarning() {
        isIdleWarning = true
        addSystemMessage("Session idle - will disconnect in 1 minute. Speak or tap to stay connected.")
    }

    private func handleIdleTimeout() {
        addSystemMessage("Session disconnected due to inactivity.")
        endSession()
    }

    private func stopAllTimers() {
        sessionTimer?.invalidate()
        sessionTimer = nil
        idleTimer?.invalidate()
        idleTimer = nil
        warningTimer?.invalidate()
        warningTimer = nil
        sessionStartTime = nil
        isIdleWarning = false
    }

    // MARK: - Messages

    private func addSystemMessage(_ content: String) {
        let message = WSMessage(type: .system, content: content)
        messages.append(message)
    }

    // MARK: - Formatting

    func formatTimeRemaining(_ seconds: Int?) -> String {
        guard let seconds = seconds else { return "" }
        let mins = seconds / 60
        let secs = seconds % 60
        return String(format: "%d:%02d", mins, secs)
    }
}

// MARK: - WebSocketManagerDelegate

extension TutorViewModel: WebSocketManagerDelegate {
    nonisolated func webSocketDidConnect() {
        Task { @MainActor in
            sessionState = .connected
            addSystemMessage("Connected to interview")
            startSessionTimer()
            do {
                try audioPlayer.configureGraph()
                try audioRecorder.prepareTap()
                try audioPlayer.startEngine()
            } catch {
                print("Failed to start audio player: \(error)")
            }
        }
    }

    nonisolated func webSocketDidDisconnect(error: Error?) {
        Task { @MainActor in
            stopAllTimers()
            audioPlayer.stop()
            if sessionState != .completed {
                addSystemMessage("Disconnected")
                sessionState = .idle
            }
        }
    }

    nonisolated func webSocketDidReceiveMessage(_ message: WSMessage) {
        Task { @MainActor in
            messages.append(message)
            resetIdleTimer()
        }
    }

    nonisolated func webSocketDidReceiveAudio(_ data: Data) {
        Task { @MainActor in
            audioPlayer.playPCMData(data)
            resetIdleTimer()
        }
    }
}

// MARK: - AudioRecorderDelegate

extension TutorViewModel: AudioRecorderDelegate {
    nonisolated func audioRecorder(_ recorder: AudioRecorder, didCapturePCMData data: Data) {
        Task { @MainActor in
            webSocketManager.sendAudio(data)
            resetIdleTimer()
        }
    }

    nonisolated func audioRecorderDidStart(_ recorder: AudioRecorder) {
        // Recording started
    }

    nonisolated func audioRecorderDidStop(_ recorder: AudioRecorder) {
        // Recording stopped
    }

    nonisolated func audioRecorder(_ recorder: AudioRecorder, didFailWithError error: Error) {
        Task { @MainActor in
            sessionState = .error(error.localizedDescription)
        }
    }
}

// MARK: - AudioPlayerDelegate

extension TutorViewModel: AudioPlayerDelegate {
    nonisolated func audioPlayerDidStartPlaying(_ player: AudioPlayer) {
        // Playback started
    }

    nonisolated func audioPlayerDidStopPlaying(_ player: AudioPlayer) {
        // Playback stopped
    }

    nonisolated func audioPlayer(_ player: AudioPlayer, didFailWithError error: Error) {
        Task { @MainActor in
            print("Audio playback error: \(error)")
        }
    }
}
