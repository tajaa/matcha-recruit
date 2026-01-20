import Foundation
import AVFoundation

protocol AudioRecorderDelegate: AnyObject {
    func audioRecorder(_ recorder: AudioRecorder, didCapturePCMData data: Data)
    func audioRecorderDidStart(_ recorder: AudioRecorder)
    func audioRecorderDidStop(_ recorder: AudioRecorder)
    func audioRecorder(_ recorder: AudioRecorder, didFailWithError error: Error)
}

enum AudioRecorderError: Error, LocalizedError {
    case microphonePermissionDenied
    case engineSetupFailed
    case formatConversionFailed

    var errorDescription: String? {
        switch self {
        case .microphonePermissionDenied:
            return "Microphone access denied. Please enable it in Settings."
        case .engineSetupFailed:
            return "Failed to set up audio recording."
        case .formatConversionFailed:
            return "Failed to convert audio format."
        }
    }
}

final class AudioRecorder {
    weak var delegate: AudioRecorderDelegate?

    private let audioEngine = AVAudioEngine()
    private var isRecording = false

    private let targetSampleRate: Double = AudioProtocol.inputSampleRate
    private let bufferSize: AVAudioFrameCount = AVAudioFrameCount(AudioProtocol.audioChunkSize)

    // MARK: - Public Methods

    func requestPermission() async -> Bool {
        return await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    func startRecording() throws {
        guard !isRecording else { return }

        do {
            try configureAudioSession()
            try setupAudioEngine()
            try audioEngine.start()
            isRecording = true
            delegate?.audioRecorderDidStart(self)
        } catch {
            delegate?.audioRecorder(self, didFailWithError: error)
            throw error
        }
    }

    func stopRecording() {
        guard isRecording else { return }

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        isRecording = false
        delegate?.audioRecorderDidStop(self)
    }

    // MARK: - Private Methods

    private func configureAudioSession() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setPreferredSampleRate(targetSampleRate)
        try session.setActive(true)
    }

    private func setupAudioEngine() throws {
        let inputNode = audioEngine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        // Create target format: 16kHz, mono, 16-bit PCM
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: targetSampleRate,
            channels: 1,
            interleaved: true
        ) else {
            throw AudioRecorderError.formatConversionFailed
        }

        // Create format converter if needed
        var converter: AVAudioConverter?
        if inputFormat.sampleRate != targetSampleRate || inputFormat.channelCount != 1 {
            guard let audioConverter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
                throw AudioRecorderError.formatConversionFailed
            }
            converter = audioConverter
        }

        // Install tap on input
        inputNode.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { [weak self] buffer, _ in
            guard let self = self else { return }
            self.processAudioBuffer(buffer, converter: converter, targetFormat: targetFormat)
        }
    }

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer, converter: AVAudioConverter?, targetFormat: AVAudioFormat) {
        let pcmData: Data

        if let converter = converter {
            // Need to convert sample rate and/or channels
            guard let convertedBuffer = convertBuffer(buffer, using: converter, to: targetFormat) else {
                return
            }
            pcmData = bufferToPCMData(convertedBuffer)
        } else {
            // Already in correct format
            pcmData = bufferToPCMData(buffer)
        }

        delegate?.audioRecorder(self, didCapturePCMData: pcmData)
    }

    private func convertBuffer(_ buffer: AVAudioPCMBuffer, using converter: AVAudioConverter, to format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let ratio = format.sampleRate / buffer.format.sampleRate
        let outputFrameCount = AVAudioFrameCount(Double(buffer.frameLength) * ratio)

        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: outputFrameCount) else {
            return nil
        }

        var error: NSError?
        let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
            outStatus.pointee = .haveData
            return buffer
        }

        converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

        if error != nil {
            return nil
        }

        return outputBuffer
    }

    private func bufferToPCMData(_ buffer: AVAudioPCMBuffer) -> Data {
        guard let int16Data = buffer.int16ChannelData else {
            // Convert from float if needed
            if let floatData = buffer.floatChannelData {
                return convertFloatToPCM(floatData[0], frameCount: Int(buffer.frameLength))
            }
            return Data()
        }

        let channelData = int16Data[0]
        let byteCount = Int(buffer.frameLength) * MemoryLayout<Int16>.size
        return Data(bytes: channelData, count: byteCount)
    }

    private func convertFloatToPCM(_ floatData: UnsafePointer<Float>, frameCount: Int) -> Data {
        var pcmData = Data(count: frameCount * MemoryLayout<Int16>.size)
        pcmData.withUnsafeMutableBytes { rawBuffer in
            let int16Buffer = rawBuffer.bindMemory(to: Int16.self)
            for i in 0..<frameCount {
                let sample = floatData[i]
                let clampedSample = max(-1.0, min(1.0, sample))
                int16Buffer[i] = Int16(clampedSample * Float(Int16.max))
            }
        }
        return pcmData
    }
}

// MARK: - Audio Session Interruption Handling

extension AudioRecorder {
    func setupInterruptionHandling() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleRouteChange),
            name: AVAudioSession.routeChangeNotification,
            object: nil
        )
    }

    @objc private func handleInterruption(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let typeValue = userInfo[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: typeValue) else {
            return
        }

        switch type {
        case .began:
            stopRecording()
        case .ended:
            guard let optionsValue = userInfo[AVAudioSessionInterruptionOptionKey] as? UInt else { return }
            let options = AVAudioSession.InterruptionOptions(rawValue: optionsValue)
            if options.contains(.shouldResume) {
                try? startRecording()
            }
        @unknown default:
            break
        }
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let reasonValue = userInfo[AVAudioSessionRouteChangeReasonKey] as? UInt,
              let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue) else {
            return
        }

        switch reason {
        case .oldDeviceUnavailable:
            // Headphones unplugged, etc.
            stopRecording()
        default:
            break
        }
    }
}
