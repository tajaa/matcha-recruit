import Foundation
import AVFoundation

protocol AudioPlayerDelegate: AnyObject {
    func audioPlayerDidStartPlaying(_ player: AudioPlayer)
    func audioPlayerDidStopPlaying(_ player: AudioPlayer)
    func audioPlayer(_ player: AudioPlayer, didFailWithError error: Error)
}

enum AudioPlayerError: Error, LocalizedError {
    case invalidAudioData
    case playbackFailed
    case audioSessionFailed

    var errorDescription: String? {
        switch self {
        case .invalidAudioData:
            return "Invalid audio data received."
        case .playbackFailed:
            return "Audio playback failed."
        case .audioSessionFailed:
            return "Failed to configure audio session."
        }
    }
}

final class AudioPlayer {
    weak var delegate: AudioPlayerDelegate?

    // Shared engine — AudioRecorder installs its input tap on this same engine
    // to avoid the simulator's "reconfig pending" I/O crash from dual engines.
    let sharedEngine = AVAudioEngine()

    private let playerNode = AVAudioPlayerNode()
    private var isPlaying = false
    private var isPrepared = false

    private let sampleRate: Double = AudioProtocol.outputSampleRate

    // MARK: - Initialization

    init() {
        // Engine setup deferred to start() — must happen after audio session is configured
    }

    // MARK: - Public Methods

    /// Configure audio session and engine graph without preparing or starting playback.
    /// Call this before installing input taps, then call `startEngine()`.
    func configureGraph() throws {
        guard !isPlaying else { return }

        do {
            try configureAudioSession()
            if !isPrepared {
                setupAudioEngine()
                isPrepared = true
            }
        } catch {
            delegate?.audioPlayer(self, didFailWithError: error)
            throw error
        }
    }

    /// Start the engine and player node. Call after `configureGraph()` and any tap setup.
    func startEngine() throws {
        guard !isPlaying else { return }

        do {
            sharedEngine.prepare()
            try sharedEngine.start()
            playerNode.play()
            isPlaying = true
            delegate?.audioPlayerDidStartPlaying(self)
        } catch {
            delegate?.audioPlayer(self, didFailWithError: error)
            throw error
        }
    }

    /// Convenience: prepare + start in one call (when no tap coordination is needed).
    func start() throws {
        try configureGraph()
        try startEngine()
    }

    func stop() {
        guard isPlaying else { return }

        playerNode.stop()
        sharedEngine.stop()
        isPlaying = false
        delegate?.audioPlayerDidStopPlaying(self)
    }

    func playPCMData(_ data: Data) {
        guard isPlaying, !data.isEmpty else { return }

        guard let buffer = createPCMBuffer(from: data) else {
            return
        }

        scheduleBuffer(buffer)
    }

    // MARK: - Private Methods

    private func configureAudioSession() throws {
        let session = AVAudioSession.sharedInstance()
        // Use .voiceChat on device for AEC/AGC/NS; use .default on simulator to
        // avoid overloading its proxy audio I/O loop.
#if targetEnvironment(simulator)
        let mode: AVAudioSession.Mode = .default
#else
        let mode: AVAudioSession.Mode = .voiceChat
#endif
        try session.setCategory(.playAndRecord, mode: mode, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setPreferredSampleRate(sampleRate)
        try session.setActive(true)
    }

    private func setupAudioEngine() {
        // Attach player node to engine
        sharedEngine.attach(playerNode)

        // Create audio format for 24kHz mono PCM
        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        ) else {
            return
        }

        // Connect player to main mixer
        sharedEngine.connect(playerNode, to: sharedEngine.mainMixerNode, format: format)

        // Access inputNode now to force full-duplex graph setup.
        // This prevents an I/O reconfiguration when the recorder installs its tap later.
        _ = sharedEngine.inputNode
    }

    private func createPCMBuffer(from data: Data) -> AVAudioPCMBuffer? {
        // Input data is 16-bit signed PCM at 24kHz
        let sampleCount = data.count / MemoryLayout<Int16>.size

        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        ),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(sampleCount))
        else {
            return nil
        }

        buffer.frameLength = AVAudioFrameCount(sampleCount)

        // Convert Int16 to Float32
        guard let floatChannelData = buffer.floatChannelData else { return nil }
        let floatBuffer = floatChannelData[0]

        data.withUnsafeBytes { rawBuffer in
            let int16Buffer = rawBuffer.bindMemory(to: Int16.self)
            for i in 0..<sampleCount {
                floatBuffer[i] = Float(int16Buffer[i]) / Float(Int16.max)
            }
        }

        return buffer
    }

    private func scheduleBuffer(_ buffer: AVAudioPCMBuffer) {
        // Sequential scheduling — each buffer plays after the previous one finishes.
        // Simpler and more reliable than host-time scheduling, which can fail
        // silently when the Core Audio I/O loop is under pressure.
        playerNode.scheduleBuffer(buffer, completionHandler: nil)
    }
}

// MARK: - Volume Control

extension AudioPlayer {
    var volume: Float {
        get { playerNode.volume }
        set { playerNode.volume = max(0, min(1, newValue)) }
    }
}
