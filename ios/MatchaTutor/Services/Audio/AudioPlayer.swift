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

    private let audioEngine = AVAudioEngine()
    private let playerNode = AVAudioPlayerNode()
    private var isPlaying = false

    private let sampleRate: Double = AudioProtocol.outputSampleRate

    // MARK: - Initialization

    init() {
        // Engine setup deferred to start() — must happen after audio session is configured
    }

    // MARK: - Public Methods

    func start() throws {
        guard !isPlaying else { return }

        do {
            try configureAudioSession()
            setupAudioEngine()
            audioEngine.prepare()
            try audioEngine.start()
            playerNode.play()
            isPlaying = true
            delegate?.audioPlayerDidStartPlaying(self)
        } catch {
            delegate?.audioPlayer(self, didFailWithError: error)
            throw error
        }
    }

    func stop() {
        guard isPlaying else { return }

        playerNode.stop()
        audioEngine.stop()
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
        // Use .default mode — .voiceChat enables heavy voice processing (AEC/AGC/NS)
        // that overloads the simulator's proxy audio I/O loop.
        // The recorder will switch to .voiceChat when recording starts.
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setPreferredSampleRate(sampleRate)
        try session.setActive(true)
    }

    private func setupAudioEngine() {
        // Attach player node to engine
        audioEngine.attach(playerNode)

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
        audioEngine.connect(playerNode, to: audioEngine.mainMixerNode, format: format)
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
