import SwiftUI
import WebKit
import AppKit

// MARK: - Reader

/// One message: header, AI quick actions (summarize; draft a reply — saved to
/// Gmail drafts and reviewed in `EmailReplySheet` before sending), and the
/// body. HTML mail renders in a locked-down web view (`EmailHTMLView`); plain
/// text renders natively with its links shortened. Hosted by the Email hub's
/// reader column. Resolves from the loaded list, falling back to a fetch by id
/// so a message read elsewhere (or re-opened after a relaunch) still opens.
struct EmailDetailView: View {
    let emailId: String
    @Environment(AppState.self) private var appState
    private let vm = EmailViewModel.shared

    @State private var loaded: EmailMessage?
    /// The single-message fetch — the only copy that carries the HTML body.
    @State private var full: EmailMessage?
    @State private var isResolving = true
    @State private var bodyReady = false
    @State private var htmlDocument: String?
    @State private var hasRemoteContent = false
    @State private var showRemoteImages = false
    @State private var summary: String?
    @State private var isSummarizing = false
    @State private var isDrafting = false
    @State private var instructions = ""
    @State private var reply: EmailDraftResponse?
    @State private var actionError: String?
    @State private var sentNote: String?
    @State private var showSendToBoard = false
    /// Bumped whenever the shown message changes, so a slow response for the
    /// previous message can't land on this one.
    @State private var generation = 0

    private var msg: EmailMessage? { full ?? vm.message(id: emailId) ?? loaded }

    var body: some View {
        Group {
            if let msg {
                content(msg)
            } else if isResolving {
                ProgressView()
                    .controlSize(.small)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                placeholder
            }
        }
        .task(id: emailId) { await open() }
        .onChange(of: showRemoteImages) { _, _ in renderHTML() }
        .sheet(item: $reply) { draft in
            EmailReplySheet(draft: draft, original: msg) {
                sentNote = "Reply sent to \(draft.to)"
            }
        }
    }

    private func open() async {
        generation += 1
        let gen = generation
        // Drop the previous message first: `msg` falls back to `loaded`, so a
        // stale copy would show the old email (with a live action bar) under
        // the new id until the fetch returns.
        loaded = nil
        full = nil
        htmlDocument = nil
        hasRemoteContent = false
        showRemoteImages = false
        bodyReady = false
        summary = nil
        actionError = nil
        sentNote = nil
        instructions = ""
        reply = nil
        showSendToBoard = false
        isSummarizing = false
        isDrafting = false
        isResolving = true
        let resolved = await vm.ensureMessage(id: emailId)
        guard gen == generation else { return }
        loaded = resolved
        isResolving = false
        // The list copy has no HTML; the single fetch does (and is cached).
        let fetched = await vm.fullMessage(id: emailId)
        guard gen == generation else { return }
        full = fetched
        renderHTML()
        bodyReady = true
    }

    private func renderHTML() {
        guard let html = full?.bodyHtml, !html.isEmpty else {
            htmlDocument = nil
            hasRemoteContent = false
            return
        }
        hasRemoteContent = EmailHTML.hasRemoteContent(html)
        htmlDocument = EmailHTML.document(html, allowRemote: showRemoteImages)
    }

    private var placeholder: some View {
        VStack(spacing: 8) {
            Image(systemName: "envelope.open")
                .font(.system(size: 28))
                .foregroundColor(appState.themeTextSecondary)
            Text("This email is no longer available")
                .font(.system(size: 13))
                .foregroundColor(appState.themeTextSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func content(_ msg: EmailMessage) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 12) {
                header(msg)
                if let atts = msg.attachments, !atts.isEmpty {
                    attachmentsRow(atts)
                }
                actionBar(msg)
                if isSummarizing || summary != nil {
                    summaryCard
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 16)
            .padding(.bottom, 12)
            Divider().opacity(0.25)
            messageBody(msg)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .sheet(isPresented: $showSendToBoard) {
            EmailSendToBoardSheet(emails: [msg]) { board in
                actionError = nil
                sentNote = "Email card created on \(board)"
            }
        }
    }

    @ViewBuilder
    private func messageBody(_ msg: EmailMessage) -> some View {
        if !bodyReady {
            ProgressView()
                .controlSize(.small)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let htmlDocument {
            VStack(spacing: 0) {
                if hasRemoteContent && !showRemoteImages {
                    remoteImagesBanner
                }
                // Mail is designed on white; it gets a white page in every theme.
                EmailHTMLView(document: htmlDocument)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(appState.themeBorder.opacity(0.4), lineWidth: 0.5)
                    )
                    .padding(12)
            }
        } else {
            EmailPlainBody(text: msg.body)
        }
    }

    private var remoteImagesBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "eye.slash").font(.system(size: 11))
            Text("Remote images are hidden, so the sender can't tell you opened this.")
                .font(.system(size: 11))
                .lineLimit(2)
            Spacer(minLength: 8)
            Button("Show images") { showRemoteImages = true }
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(appState.themeAccent)
        }
        .foregroundColor(appState.themeTextSecondary)
        .padding(.horizontal, 16)
        .padding(.vertical, 7)
        .background(appState.themeCard.opacity(0.5))
    }

    private func header(_ msg: EmailMessage) -> some View {
        let info = vm.rowInfo(for: msg)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(msg.subject.isEmpty ? "(no subject)" : msg.subject)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Button {
                    showSendToBoard = true
                } label: {
                    Label("Send to board", systemImage: "rectangle.stack.badge.plus")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .help("Create an Email card with this message attached, for you or AutoPR to work")
            }
            HStack(spacing: 10) {
                EmailAvatar(initial: info.initial, tint: info.tint, size: 32)
                VStack(alignment: .leading, spacing: 1) {
                    Text(info.senderName)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                    Text(info.senderAddress)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                        .textSelection(.enabled)
                }
                Spacer(minLength: 8)
                if let bucket = vm.bucket(of: msg.id) {
                    EmailBucketChip(bucket: bucket)
                        .help(vm.triage[msg.id]?.reason ?? "")
                }
                Text(info.fullDate)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    private func attachmentsRow(_ atts: [EmailAttachment]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(atts, id: \.attachmentId) { att in
                    Label(att.filename, systemImage: "paperclip")
                        .font(.system(size: 11))
                        .lineLimit(1)
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(appState.themeCard)
                        .cornerRadius(5)
                }
            }
        }
        .help("Attachments stay in Gmail")
    }

    // MARK: AI action bar

    private func actionBar(_ msg: EmailMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                TextField("Reply instructions (optional)…", text: $instructions)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .frame(maxWidth: .infinity)
                    .onSubmit { draft(msg) }
                    .help("e.g. \"say yes to Friday, keep it short\"")
                actionButton("Summarize", icon: "text.alignleft", busy: isSummarizing) { summarize(msg) }
                actionButton("Draft reply", icon: "arrowshape.turn.up.left", busy: isDrafting, primary: true) { draft(msg) }
            }
            if let actionError {
                statusLine(icon: "exclamationmark.triangle.fill", text: actionError, color: .orange)
            } else if let sentNote {
                statusLine(icon: "checkmark.circle.fill", text: sentNote, color: .green)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(appState.themeAccent.opacity(0.06))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(appState.themeAccent.opacity(0.25), lineWidth: 1)
        )
        .cornerRadius(6)
    }

    private func actionButton(
        _ title: String,
        icon: String,
        busy: Bool,
        primary: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if busy {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: appState.canEmailAI ? icon : "lock.fill")
                        .font(.system(size: 10))
                }
                Text(title).font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(primary ? appState.themeOnAccent : appState.themeAccent)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(primary ? appState.themeAccent : appState.themeAccent.opacity(0.12))
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .help(appState.canEmailAI ? "" : "Email AI needs Lite")
    }

    private func statusLine(icon: String, text: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9)).foregroundColor(color)
            Text(text).font(.system(size: 10)).foregroundColor(color)
            Spacer()
        }
    }

    private var summaryCard: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "sparkles")
                .font(.system(size: 11))
                .foregroundColor(appState.themeAccent)
                .padding(.top, 1)
            if isSummarizing {
                Text("Summarizing…")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            } else {
                let text = summary ?? ""
                Text(text.isEmpty ? "Summary unavailable — try again." : text)
                    .font(.system(size: 12))
                    .foregroundColor(text.isEmpty ? appState.themeTextSecondary : appState.themeText)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer(minLength: 0)
            if !isSummarizing {
                Button {
                    summary = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Hide summary")
            }
        }
        .padding(12)
        .background(appState.themeAccent.opacity(0.05))
        .cornerRadius(6)
    }

    // MARK: actions

    private func requireEmailAI() -> Bool {
        guard appState.canEmailAI else {
            appState.presentPaywall(for: "email_ai")
            return false
        }
        return true
    }

    private func summarize(_ msg: EmailMessage) {
        guard requireEmailAI(), !isSummarizing else { return }
        isSummarizing = true
        actionError = nil
        let gen = generation
        let id = msg.id
        Task {
            do {
                let resp = try await EmailService.shared.summarize(emailId: id)
                guard gen == generation else { return }
                summary = resp.summary.trimmingCharacters(in: .whitespacesAndNewlines)
            } catch {
                guard gen == generation else { return }
                actionError = error.localizedDescription
            }
            if gen == generation { isSummarizing = false }
        }
    }

    private func draft(_ msg: EmailMessage) {
        guard requireEmailAI(), !isDrafting else { return }
        isDrafting = true
        actionError = nil
        sentNote = nil
        let gen = generation
        let id = msg.id
        let text = instructions
        Task {
            do {
                let resp = try await EmailService.shared.draftReply(emailId: id, instructions: text)
                guard gen == generation else { return }
                reply = resp
            } catch {
                guard gen == generation else { return }
                actionError = error.localizedDescription
            }
            if gen == generation { isDrafting = false }
        }
    }
}

// MARK: - Bodies

/// Wraps a sender's HTML for `EmailHTMLView`. The CSP is the content
/// boundary: no scripts, frames, forms or external stylesheets, and no remote
/// loads at all — tracking pixels included — until the reader asks for images.
enum EmailHTML {
    static func document(_ html: String, allowRemote: Bool) -> String {
        let images = allowRemote ? "data: cid: https: http:" : "data: cid:"
        let fonts = allowRemote ? "data: https:" : "data:"
        let csp = "default-src 'none'; style-src 'unsafe-inline'; img-src \(images); font-src \(fonts); form-action 'none'"
        return """
        <!doctype html><html><head><meta charset="utf-8">
        <meta http-equiv="Content-Security-Policy" content="\(csp)">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
        html { background: #ffffff; }
        body { margin: 0; padding: 18px 20px; color: #1d1d1f; overflow-wrap: anywhere;
               font: 14px/1.5 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; }
        img { max-width: 100%; height: auto; }
        pre { white-space: pre-wrap; }
        </style></head><body>\(html)</body></html>
        """
    }

    private static let remotePattern = try? NSRegularExpression(
        pattern: #"(?:src|srcset|background)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//"#,
        options: .caseInsensitive
    )

    /// Anything that would phone home if loaded: an image, a background, a font.
    static func hasRemoteContent(_ html: String) -> Bool {
        guard let remotePattern else { return false }
        return remotePattern.firstMatch(in: html, range: NSRange(html.startIndex..., in: html)) != nil
    }
}

/// Sender-written HTML rendered with nothing live: no JavaScript, an
/// ephemeral data store (no cookies to set or read), the `EmailHTML` CSP, and
/// every link handed to the system browser instead of navigating in place.
struct EmailHTMLView: NSViewRepresentable {
    let document: String

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        config.websiteDataStore = .nonPersistent()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = false
        webView.allowsLinkPreview = false
        context.coordinator.load(document, in: webView)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        context.coordinator.load(document, in: webView)
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        private var loaded: String?
        /// Set just before `loadHTMLString`; the one main-frame navigation it
        /// starts is the only one allowed to load in place.
        private var documentLoadPending = false

        func load(_ document: String, in webView: WKWebView) {
            guard loaded != document else { return }
            loaded = document
            documentLoadPending = true
            webView.loadHTMLString(document, baseURL: nil)
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
        ) {
            // A clicked link opens in the default browser. Only our own
            // document load navigates in place; anything else the page tries —
            // a meta refresh, a frame, a form post — is refused.
            if navigationAction.navigationType == .linkActivated {
                if let url = navigationAction.request.url { Self.openExternally(url) }
                decisionHandler(.cancel)
                return
            }
            if documentLoadPending, navigationAction.targetFrame?.isMainFrame == true {
                documentLoadPending = false
                decisionHandler(.allow)
                return
            }
            decisionHandler(.cancel)
        }

        /// `target="_blank"` links ask for a new web view; open them outside.
        func webView(
            _ webView: WKWebView,
            createWebViewWith configuration: WKWebViewConfiguration,
            for navigationAction: WKNavigationAction,
            windowFeatures: WKWindowFeatures
        ) -> WKWebView? {
            if let url = navigationAction.request.url { Self.openExternally(url) }
            return nil
        }

        private static func openExternally(_ url: URL) {
            if url.scheme?.lowercased() == "mailto" {
                NSWorkspace.shared.open(url)
            } else {
                SafeURL.open(url.absoluteString)   // http(s) only
            }
        }
    }
}

/// A plain-text body, natively: themed, selectable, and each URL shown as its
/// host ("pinterest.com/…") instead of a wall of tracking parameters.
struct EmailPlainBody: View {
    let text: String
    @Environment(AppState.self) private var appState
    @State private var rendered = AttributedString()

    var body: some View {
        ScrollView {
            Text(rendered)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText)
                .tint(appState.themeAccent)
                .lineSpacing(3)
                .textSelection(.enabled)
                .frame(maxWidth: 720, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20)
                .padding(.vertical, 16)
        }
        .environment(\.openURL, OpenURLAction { url in
            SafeURL.open(url.absoluteString) ? .handled : .discarded
        })
        .task(id: text) { rendered = EmailPlainText.linkified(text) }
    }
}

enum EmailPlainText {
    static func linkified(_ raw: String) -> AttributedString {
        let text = raw
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: #"\n{3,}"#, with: "\n\n", options: .regularExpression)
        let ns = text as NSString
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        var out = AttributedString()
        var cursor = 0
        for match in detector?.matches(in: text, range: NSRange(location: 0, length: ns.length)) ?? [] {
            guard let url = match.url,
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https" else { continue }
            if match.range.location > cursor {
                out += AttributedString(ns.substring(with: NSRange(location: cursor, length: match.range.location - cursor)))
            }
            var link = AttributedString(shortLabel(url))
            link.link = url
            out += link
            cursor = match.range.location + match.range.length
        }
        if cursor < ns.length {
            out += AttributedString(ns.substring(from: cursor))
        }
        return out
    }

    /// "pinterest.com/…" for a URL with a path or query; the bare host otherwise.
    static func shortLabel(_ url: URL) -> String {
        var host = url.host ?? url.absoluteString
        if host.hasPrefix("www.") { host.removeFirst(4) }
        let hasMore = !(url.path.isEmpty || url.path == "/") || url.query != nil
        return hasMore ? "\(host)/…" : host
    }
}
