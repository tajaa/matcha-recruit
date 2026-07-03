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

    // Shared engine from AudioPlayer — avoids dual-engine I/O conflicts
    private var sharedEngine: AVAudioEngine?
    private var isRecording = false
    private var isTapInstalled = false
    private var debugBufferCount = 0

    private let targetSampleRate: Double = AudioProtocol.inputSampleRate
    private let bufferSize: AVAudioFrameCount = AVAudioFrameCount(AudioProtocol.audioChunkSize)

    // MARK: - Public Methods

    func setSharedEngine(_ engine: AVAudioEngine) {
        self.sharedEngine = engine
    }

    func requestPermission() async -> Bool {
        return await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    func prepareTap() throws {
        guard let engine = sharedEngine else {
            throw AudioRecorderError.engineSetupFailed
        }
        guard !isTapInstalled else { return }

        try installInputTap(on: engine)
        isTapInstalled = true
    }

    func startRecording() throws {
        guard !isRecording else { return }
        guard let engine = sharedEngine else {
            throw AudioRecorderError.engineSetupFailed
        }

        do {
            try prepareTap()

            // Start the shared engine after the tap is installed.
            if !engine.isRunning {
                try engine.start()
            }
            isRecording = true
            delegate?.audioRecorderDidStart(self)
        } catch {
            delegate?.audioRecorder(self, didFailWithError: error)
            throw error
        }
    }

    func stopRecording() {
        guard isRecording else { return }

        isRecording = false
        delegate?.audioRecorderDidStop(self)
    }

    func removeTap() {
        guard isTapInstalled, let engine = sharedEngine else { return }
        engine.inputNode.removeTap(onBus: 0)
        isTapInstalled = false
    }

    // MARK: - Private Methods

    private func installInputTap(on engine: AVAudioEngine) throws {
        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            print("[AudioRecorder] Invalid input format: \(inputFormat.sampleRate)Hz, \(inputFormat.channelCount)ch")
            throw AudioRecorderError.engineSetupFailed
        }

        // Create target format: 16kHz, mono, 16-bit PCM
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: targetSampleRate,
            channels: 1,
            interleaved: true
        ) else {
            throw AudioRecorderError.formatConversionFailed
        }

        print("[AudioRecorder] Input format: \(inputFormat.sampleRate)Hz, \(inputFormat.channelCount)ch, \(inputFormat)")

        // Always create converter to normalize format for the backend.
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            print("[AudioRecorder] Failed to create converter from \(inputFormat) to \(targetFormat)")
            throw AudioRecorderError.formatConversionFailed
        }
        print("[AudioRecorder] Converter created: \(inputFormat.sampleRate)Hz → \(targetFormat.sampleRate)Hz")

        // Install tap on input — engine will be started after the graph is complete.
        inputNode.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { [weak self] buffer, _ in
            guard let self = self else { return }
            self.processAudioBuffer(buffer, converter: converter, targetFormat: targetFormat)
        }
    }

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer, converter: AVAudioConverter?, targetFormat: AVAudioFormat) {
        guard isRecording else { return }

        let pcmData: Data

        guard let converter = converter else { return }
        guard let convertedBuffer = convertBuffer(buffer, using: converter, to: targetFormat) else {
            return
        }
        pcmData = bufferToPCMData(convertedBuffer)

        debugBufferCount += 1
        if debugBufferCount % 50 == 0 {
            // Calculate RMS of raw input to verify mic captures real audio
            var rmsDB: Float = -999
            if let floatData = buffer.floatChannelData {
                let frames = Int(buffer.frameLength)
                var sum: Float = 0
                for i in 0..<frames {
                    let s = floatData[0][i]
                    sum += s * s
                }
                let rms = sqrtf(sum / Float(max(frames, 1)))
                rmsDB = 20 * log10f(max(rms, 1e-10))
            }
            print("[AudioRecorder] buf#\(debugBufferCount) | RMS: \(String(format: "%.1f", rmsDB)) dBFS | \(pcmData.count) bytes (\(convertedBuffer.frameLength) frames)")
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
        var hasProvidedData = false
        let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
            if hasProvidedData {
                outStatus.pointee = .noDataNow
                return nil
            }
            hasProvidedData = true
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
