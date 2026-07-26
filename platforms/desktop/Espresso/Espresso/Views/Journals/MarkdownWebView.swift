import SwiftUI
import WebKit

/// Reading-mode renderer for journal documents. Loads a bundled, fully offline
/// HTML template (markdown-it + highlight.js + Mermaid + MathJax) into a
/// WKWebView and renders the markdown source — so LaTeX (`$…$` / `$$…$$`),
/// fenced code (syntax-highlighted) and ```mermaid``` diagrams all display.
/// The editor keeps editing plain markdown; this only renders.
struct MarkdownWebView: NSViewRepresentable {
    let content: String
    /// Theme-derived hex colors + dark flag, so the preview matches the app.
    let textHex: String
    let secondaryHex: String
    let accentHex: String
    let dark: Bool
    let fontSize: CGFloat

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.navigationDelegate = context.coordinator
        wv.underPageBackgroundColor = .clear   // let the app theme show through
        if let url = Bundle.main.url(forResource: "journal_preview", withExtension: "html", subdirectory: "JournalPreview") {
            wv.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        }
        return wv
    }

    func updateNSView(_ wv: WKWebView, context: Context) {
        context.coordinator.parent = self
        // Only re-render when something actually changed (updateNSView fires on
        // every SwiftUI pass) and the page has finished loading.
        let key = "\(textHex)|\(secondaryHex)|\(accentHex)|\(dark)|\(fontSize)|\(content.hashValue)"
        guard context.coordinator.loaded, context.coordinator.lastKey != key else { return }
        context.coordinator.lastKey = key
        render(in: wv)
    }

    func render(in wv: WKWebView) {
        guard let doc = jsLiteral(content) else { return }
        let theme = """
        {"dark": \(dark), "text": "\(textHex)", "secondary": "\(secondaryHex)", \
        "accent": "\(accentHex)", "size": "\(Int(fontSize))px"}
        """
        wv.evaluateJavaScript("window.__renderDoc(\(doc), \(theme));", completionHandler: nil)
    }

    /// JSON-encode the markdown into a JS-safe quoted string literal.
    private func jsLiteral(_ s: String) -> String? {
        guard let data = try? JSONEncoder().encode(s) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var parent: MarkdownWebView
        var loaded = false
        var lastKey = ""
        init(_ parent: MarkdownWebView) { self.parent = parent }

        func webView(_ wv: WKWebView, didFinish navigation: WKNavigation!) {
            loaded = true
            lastKey = "\(parent.textHex)|\(parent.secondaryHex)|\(parent.accentHex)|\(parent.dark)|\(parent.fontSize)|\(parent.content.hashValue)"
            parent.render(in: wv)
        }
    }
}

extension MarkdownWebView {
    /// `#RRGGBB` for a SwiftUI Color (sRGB). Falls back to black on catalog
    /// colors that can't be converted.
    static func hex(_ color: Color) -> String {
        let ns = NSColor(color).usingColorSpace(.sRGB) ?? .black
        let r = Int((ns.redComponent * 255).rounded())
        let g = Int((ns.greenComponent * 255).rounded())
        let b = Int((ns.blueComponent * 255).rounded())
        return String(format: "#%02X%02X%02X", r, g, b)
    }

    /// Dark appearance if the body text color is light (works even when the
    /// theme background is clear).
    static func isDark(text: Color) -> Bool {
        let ns = NSColor(text).usingColorSpace(.sRGB) ?? .black
        let lum = 0.299 * ns.redComponent + 0.587 * ns.greenComponent + 0.114 * ns.blueComponent
        return lum > 0.55
    }
}
