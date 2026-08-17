import SwiftUI
import WebKit

struct CzSelection: Equatable {
    let block: Int
    let field: String?
    let element: String?
    let kind: String
    let start: Int?
    let end: Int?
    let text: String?
}

enum CzCommand {
    case mode(String)
    case highlight(Int)
    case clear
}

struct PreviewWebView: UIViewRepresentable {
    let html: String
    var onSelect: (CzSelection) -> Void
    var onReady: () -> Void
    @Binding var command: CzCommand?

    func makeCoordinator() -> Coordinator { Coordinator(onSelect: onSelect, onReady: onReady) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "cz")
        controller.addUserScript(WKUserScript(source: """
        window.addEventListener('message', function(e) {
          try { window.webkit.messageHandlers.cz.postMessage(e.data) } catch (_) {}
        });
        """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        configuration.userContentController = controller
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = .clear
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        if context.coordinator.loadedHTML != html, !html.isEmpty {
            context.coordinator.loadedHTML = html
            let offset = view.scrollView.contentOffset
            view.loadHTMLString(html, baseURL: APIClient.shared.assetOriginURL)
            context.coordinator.restoreOffset = offset
        }
        if let command {
            context.coordinator.send(command, to: view)
            DispatchQueue.main.async { self.command = nil }
        }
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        let onSelect: (CzSelection) -> Void
        let onReady: () -> Void
        var loadedHTML = ""
        var restoreOffset = CGPoint.zero

        init(onSelect: @escaping (CzSelection) -> Void, onReady: @escaping () -> Void) {
            self.onSelect = onSelect
            self.onReady = onReady
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let payload = message.body as? [String: Any], payload["type"] as? String == "cz-selection" || payload["type"] as? String == "cz-select" else { return }
            onSelect(CzSelection(
                block: payload["block"] as? Int ?? -1,
                field: payload["field"] as? String,
                element: payload["element"] as? String,
                kind: payload["kind"] as? String ?? "element",
                start: payload["start"] as? Int,
                end: payload["end"] as? Int,
                text: payload["text"] as? String
            ))
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            webView.scrollView.setContentOffset(restoreOffset, animated: false)
            onReady()
        }

        func send(_ command: CzCommand, to view: WKWebView) {
            let message: [String: Any]
            switch command {
            case .mode(let mode): message = ["type": "cz-mode", "mode": mode]
            case .highlight(let index): message = ["type": "cz-highlight", "block": index]
            case .clear: message = ["type": "cz-clear"]
            }
            guard let data = try? JSONSerialization.data(withJSONObject: message),
                  let json = String(data: data, encoding: .utf8) else { return }
            view.evaluateJavaScript("window.postMessage(\(json), '*')")
        }
    }
}

private extension APIClient {
    var assetOriginURL: URL? { URL(string: assetOrigin) }
}
