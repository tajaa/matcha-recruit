import Foundation
import Combine

enum WebSocketState {
    case disconnected
    case connecting
    case connected
    case disconnecting
}

protocol WebSocketManagerDelegate: AnyObject {
    func webSocketDidConnect()
    func webSocketDidDisconnect(error: Error?)
    func webSocketDidReceiveMessage(_ message: WSMessage)
    func webSocketDidReceiveAudio(_ data: Data)
}

final class WebSocketManager: NSObject {
    weak var delegate: WebSocketManagerDelegate?

    private(set) var state: WebSocketState = .disconnected
    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession!
    private var debugAudioSendCount = 0

    #if DEBUG
    private let baseWSURL = "ws://localhost:8001/api/ws/interview"
    #else
    private let baseWSURL = "wss://api.matcha.example.com/api/ws/interview"
    #endif

    override init() {
        super.init()
        let config = URLSessionConfiguration.default
        session = URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }

    // MARK: - Connection

    func connect(interviewId: String) {
        guard state == .disconnected else { return }

        guard let url = URL(string: "\(baseWSURL)/\(interviewId)") else {
            print("Invalid WebSocket URL")
            return
        }

        state = .connecting
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        receiveMessage()
    }

    func disconnect() {
        guard state == .connected || state == .connecting else { return }
        state = .disconnecting
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
    }

    // MARK: - Sending

    func sendAudio(_ pcmData: Data) {
        guard state == .connected else { return }

        // Prepend the client audio prefix byte
        var framedData = Data([AudioProtocol.clientAudioPrefix])
        framedData.append(pcmData)

        debugAudioSendCount += 1
        if debugAudioSendCount % 50 == 0 {
            print("[WebSocket] Sending audio frame: \(framedData.count) bytes")
        }

        let message = URLSessionWebSocketTask.Message.data(framedData)
        webSocketTask?.send(message) { error in
            if let error = error {
                print("WebSocket send error: \(error)")
            }
        }
    }

    func sendMessage(_ text: String) {
        guard state == .connected else { return }

        let message = URLSessionWebSocketTask.Message.string(text)
        webSocketTask?.send(message) { error in
            if let error = error {
                print("WebSocket send error: \(error)")
            }
        }
    }

    // MARK: - Receiving

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self = self else { return }

            switch result {
            case .success(let message):
                self.handleMessage(message)
                // Continue listening
                if self.state == .connected {
                    self.receiveMessage()
                }
            case .failure(let error):
                print("WebSocket receive error: \(error)")
                self.handleDisconnection(error: error)
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .data(let data):
            handleBinaryMessage(data)
        case .string(let text):
            handleTextMessage(text)
        @unknown default:
            break
        }
    }

    private func handleBinaryMessage(_ data: Data) {
        guard !data.isEmpty else { return }

        let prefix = data[0]

        switch prefix {
        case AudioProtocol.serverAudioPrefix:
            // Audio from server - strip prefix and forward
            let audioData = data.subdata(in: 1..<data.count)
            delegate?.webSocketDidReceiveAudio(audioData)
        case AudioProtocol.clientAudioPrefix:
            // Echo of client audio - ignore
            break
        default:
            // Unknown prefix - treat as raw audio
            delegate?.webSocketDidReceiveAudio(data)
        }
    }

    private func handleTextMessage(_ text: String) {
        guard let data = text.data(using: .utf8) else { return }

        do {
            let message = try JSONDecoder().decode(WSMessage.self, from: data)
            delegate?.webSocketDidReceiveMessage(message)
        } catch {
            print("Failed to decode WebSocket message: \(error)")
            // Create a system message for unparseable content
            let systemMessage = WSMessage(type: .system, content: text)
            delegate?.webSocketDidReceiveMessage(systemMessage)
        }
    }

    private func handleDisconnection(error: Error?) {
        state = .disconnected
        webSocketTask = nil
        delegate?.webSocketDidDisconnect(error: error)
    }
}

// MARK: - URLSessionWebSocketDelegate

extension WebSocketManager: URLSessionWebSocketDelegate {
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        print("[WebSocket] Connected to \(webSocketTask.originalRequest?.url?.absoluteString ?? "unknown")")
        state = .connected
        delegate?.webSocketDidConnect()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        handleDisconnection(error: nil)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            handleDisconnection(error: error)
        }
    }
}
