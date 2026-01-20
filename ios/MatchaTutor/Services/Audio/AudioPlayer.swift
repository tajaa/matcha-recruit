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
    private let playaheadSeconds: TimeInterval = 0.25
    private let turnStartDelaySeconds: TimeInterval = 0.5

    private var nextScheduleTime: AVAudioTime?
    private var lastScheduleHostTime: UInt64 = 0

    // MARK: - Initialization

    init() {
        setupAudioEngine()
    }

    // MARK: - Public Methods

    func start() throws {
        guard !isPlaying else { return }

        do {
            try configureAudioSession()
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
        nextScheduleTime = nil
        lastScheduleHostTime = 0
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
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
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
        let now = mach_absolute_time()
        var timeInfo = mach_timebase_info_data_t()
        mach_timebase_info(&timeInfo)

        let nanosPerTick = Double(timeInfo.numer) / Double(timeInfo.denom)

        // Calculate schedule time
        let playaheadNanos = UInt64(playaheadSeconds * 1_000_000_000)
        let turnDelayNanos = UInt64(turnStartDelaySeconds * 1_000_000_000)

        let graceNanos = UInt64(0.05 * 1_000_000_000)
        let isNewTurn = lastScheduleHostTime == 0 || (now > lastScheduleHostTime + graceNanos)

        var scheduleHostTime: UInt64
        if isNewTurn {
            scheduleHostTime = now + playaheadNanos + turnDelayNanos
        } else {
            scheduleHostTime = max(lastScheduleHostTime, now + playaheadNanos)
        }

        // Convert to ticks
        let scheduleTicks = UInt64(Double(scheduleHostTime) / nanosPerTick)

        let scheduleTime = AVAudioTime(hostTime: scheduleTicks)
        playerNode.scheduleBuffer(buffer, at: scheduleTime, options: [], completionHandler: nil)

        // Update for next buffer
        let bufferDurationNanos = UInt64(Double(buffer.frameLength) / sampleRate * 1_000_000_000)
        lastScheduleHostTime = scheduleHostTime + bufferDurationNanos
    }
}

// MARK: - Volume Control

extension AudioPlayer {
    var volume: Float {
        get { playerNode.volume }
        set { playerNode.volume = max(0, min(1, newValue)) }
    }
}
