import SwiftUI
import UserNotifications
import UniformTypeIdentifiers
import AppKit

/// Macos Settings scene — opened via Cmd+, or the "Werk → Settings…"
/// menu. Three tabs: Notifications, Account, About. Surfaces toggles
/// that were previously only flippable via UserDefaults directly.
struct SettingsView: View {
    @Environment(AppState.self) private var appState
    /// Whether the server lets this account buy through agent cards (admins
    /// plus an allowlist), or it already has saved cards.
    @State private var paymentCardsAvailable = false

    var body: some View {
        TabView {
            NotificationsSettingsTab()
                .tabItem { Label("Notifications", systemImage: "bell") }
            AppearanceSettingsTab()
                .tabItem { Label("Appearance", systemImage: "paintpalette") }
            AccountSettingsTab()
                .tabItem { Label("Account", systemImage: "person.circle") }
            ConnectorsSettingsTab()
                .tabItem { Label("AI Connectors", systemImage: "powerplug") }
            // Agent-card purchases are internal-only in v1; the server decides who.
            if appState.currentUser?.role == "admin" || paymentCardsAvailable {
                PaymentCardsSettingsTab()
                    .tabItem { Label("Payment Cards", systemImage: "creditcard") }
            }
            AboutSettingsTab()
                .tabItem { Label("About", systemImage: "info.circle") }
        }
        .frame(width: 480, height: 360)
        .task(id: appState.currentUser?.email) {
            guard let state = try? await MatchaWorkService.shared.paymentCards() else { return }
            paymentCardsAvailable = state.enabled || !state.cards.isEmpty
        }
    }
}

// MARK: - Payment Cards

/// Saved cards for agent-card purchases. When Espresso asks in a project chat
/// "want me to buy it?", you reply with a card's last 4 digits. The number is
/// sent once, encrypted on the server and never shown again; there is no
/// security-code field, and card numbers never go through chat.
private struct PaymentCardsSettingsTab: View {
    @State private var state: MWPaymentCardsState?
    @State private var number = ""
    @State private var expiry = ""
    @State private var label = ""
    @State private var busy = false
    @State private var message: String?

    var body: some View {
        Form {
            Section {
                if let state {
                    if state.cards.isEmpty {
                        Text("No saved cards.").foregroundColor(.secondary)
                    }
                    ForEach(state.cards) { card in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(card.brandName) ending \(card.last4)")
                                Text(Self.caption(card)).font(.caption).foregroundColor(.secondary)
                            }
                            Spacer()
                            Button("Remove") { Task { await remove(card) } }
                                .disabled(busy)
                        }
                    }
                } else if message == nil {
                    ProgressView().controlSize(.small)
                }
            } header: {
                Text("Saved cards").font(.subheadline).bold()
            } footer: {
                Text("When Espresso asks in a project chat whether to buy something, reply with a card's last 4 digits. Never paste a card number in chat.")
                    .font(.caption).foregroundColor(.secondary)
            }
            if let state, state.enabled {
                Section {
                    if state.configured {
                        // Grouped macOS forms render a plain TextField as a
                        // row label plus an invisible, borderless trailing
                        // box; bordered fields with prompts are clickable.
                        TextField("Card number", text: $number, prompt: Text("4242 4242 4242 4242"))
                            .textFieldStyle(.roundedBorder)
                        TextField("Expiry", text: $expiry, prompt: Text("MM/YY"))
                            .textFieldStyle(.roundedBorder)
                        TextField("Label", text: $label, prompt: Text("Optional, e.g. Stripe test"))
                            .textFieldStyle(.roundedBorder)
                        Button(busy ? "Saving…" : "Save card") { Task { await save() } }
                            .disabled(busy || number.isEmpty || expiry.isEmpty)
                    } else {
                        Text("Card storage isn't set up on this server yet.").foregroundColor(.orange)
                    }
                } header: {
                    Text("Add a card").font(.subheadline).bold()
                } footer: {
                    Text("Encrypted on the server and never shown again. No security code is asked for or stored.")
                        .font(.caption).foregroundColor(.secondary)
                }
            }
            if let message {
                Text(message).font(.caption).foregroundColor(.secondary)
            }
        }
        .formStyle(.grouped)
        .task { await load() }
    }

    private static func caption(_ card: MWPaymentCard) -> String {
        let expiry = String(format: "%02d/%02d", card.expMonth, card.expYear % 100)
        return card.label.isEmpty ? "Expires \(expiry)" : "\(card.label) · expires \(expiry)"
    }

    /// "03/31" or "3/2031" → (3, 2031).
    static func parseExpiry(_ text: String) -> (month: Int, year: Int)? {
        let parts = text.split(separator: "/").map { $0.trimmingCharacters(in: .whitespaces) }
        guard parts.count == 2, let month = Int(parts[0]), let year = Int(parts[1]),
              (1...12).contains(month), parts[1].count == 2 || parts[1].count == 4 else {
            return nil
        }
        return (month, parts[1].count == 2 ? 2000 + year : year)
    }

    private func load() async {
        do {
            state = try await MatchaWorkService.shared.paymentCards()
        } catch {
            message = (error as? APIError)?.serverDetail ?? error.localizedDescription
        }
    }

    private func save() async {
        guard let (month, year) = Self.parseExpiry(expiry) else {
            message = "Enter the expiry as MM/YY."
            return
        }
        busy = true
        message = nil
        defer { busy = false }
        do {
            _ = try await MatchaWorkService.shared.addPaymentCard(
                number: number, expMonth: month, expYear: year, label: label
            )
            number = ""
            expiry = ""
            label = ""
            message = "Card saved."
            await load()
        } catch {
            message = (error as? APIError)?.serverDetail ?? error.localizedDescription
        }
    }

    private func remove(_ card: MWPaymentCard) async {
        busy = true
        defer { busy = false }
        do {
            try await MatchaWorkService.shared.deletePaymentCard(id: card.id)
            await load()
        } catch {
            message = (error as? APIError)?.serverDetail ?? error.localizedDescription
        }
    }
}

// MARK: - AI Connectors

/// Local Codex owns ChatGPT sign-in. External assistants connect through
/// Matcha's consent page. Vendor credentials never pass through Matcha's API.
private struct ConnectorsSettingsTab: View {
    @State private var state: MWConnectorsState?
    @State private var error: String?
    @State private var busyClientId: String?
    @State private var copied: String?

    var body: some View {
        Form {
            Section {
                CodexAccountControls()
            } header: {
                Text("Codex in Espresso").font(.subheadline).bold()
            } footer: {
                Text("Research runs on your ChatGPT plan while Espresso is open.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section {
                if let state {
                    if state.grants.isEmpty {
                        Text("No assistants connected yet.")
                            .foregroundColor(.secondary)
                    }
                    ForEach(state.grants) { grant in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(grant.clientName)
                                Text(Self.kindLabel(grant.kind))
                                    .font(.caption).foregroundColor(.secondary)
                            }
                            Spacer()
                            Button(busyClientId == grant.clientId ? "Disconnecting…" : "Disconnect") {
                                Task { await disconnect(grant.clientId) }
                            }
                            .disabled(busyClientId != nil)
                        }
                    }
                } else if error == nil {
                    ProgressView().controlSize(.small)
                }
                if let error {
                    Text(error).font(.caption).foregroundColor(.red)
                }
            } header: {
                Text("Connected").font(.subheadline).bold()
            } footer: {
                Text("Research runs on your own plan; Matcha never sees that account. Changing your password disconnects every assistant.")
                    .font(.caption).foregroundColor(.secondary)
            }

            if let state {
                Section {
                    copyRow("Connector URL", state.mcpUrl)
                    Text("Claude: Settings → Connectors → Add custom connector → paste the URL.")
                        .font(.caption)
                    Text("ChatGPT: Settings → Security and login → Developer mode (once), then chatgpt.com/plugins → + → Create MCP App → paste the URL, OAuth.")
                        .font(.caption)
                    copyRow("Claude Code (then /mcp to sign in)", state.claudeCodeCommand)
                    ForEach(Array(state.codexCommands.enumerated()), id: \.offset) { index, command in
                        copyRow(index == 0 ? "Codex CLI" : "Codex sign-in (opens Matcha to approve)", command)
                    }
                } header: {
                    Text("Connect an assistant").font(.subheadline).bold()
                }
            }
        }
        .formStyle(.grouped)
        .task { await load() }
    }

    @ViewBuilder
    private func copyRow(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundColor(.secondary)
            HStack {
                Text(value)
                    .font(.system(size: 11, design: .monospaced))
                    .textSelection(.enabled)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                Button(copied == value ? "Copied" : "Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(value, forType: .string)
                    copied = value
                }
                .controlSize(.small)
            }
        }
    }

    private static func kindLabel(_ kind: String) -> String {
        switch kind {
        case "claude": return "Claude"
        case "chatgpt": return "ChatGPT"
        case "claude_code": return "Claude Code"
        case "codex": return "Codex"
        default: return "Other assistant"
        }
    }

    private func load() async {
        do {
            state = try await MatchaWorkService.shared.listConnectors()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func disconnect(_ clientId: String) async {
        busyClientId = clientId
        defer { busyClientId = nil }
        do {
            try await MatchaWorkService.shared.disconnectConnector(clientId: clientId)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Appearance

private struct AppearanceSettingsTab: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var appState = appState
        Form {
            Section {
                Picker("Theme", selection: $appState.appTheme) {
                    Text("Platinum").tag("platinum")
                    Text("Dark").tag("dark")
                    Text("Light").tag("light")
                    Text("Cappuchin").tag("cappuchin")
                    Text("Graphite").tag("graphite")
                }
                .pickerStyle(.radioGroup)
            } header: {
                Text("UI Theme").font(.subheadline).bold()
            } footer: {
                Text("Choose your preferred workspace color theme. Platinum is the signature cool light-gray look; Cappuchin provides a cozy warm coffee atmosphere; Graphite is a minimalist neutral grayscale.")
                    .font(.caption).foregroundColor(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Notifications

private struct NotificationsSettingsTab: View {
    /// Mirror the three flags from `ChannelNotificationManager`. Stored
    /// directly in UserDefaults under the same keys the existing send /
    /// observer paths read.
    @State private var appNotificationsEnabled = ChannelNotificationManager.shared.appNotificationsEnabled
    @State private var channelNotificationsEnabled = ChannelNotificationManager.shared.isEnabled
    @State private var channelSoundEnabled = ChannelNotificationManager.shared.soundEnabled
    @State private var promptSuppressed = ChannelNotificationManager.shared.promptSuppressed
    @State private var permissionStatus: String = "checking…"

    var body: some View {
        Form {
            Section {
                Toggle(isOn: $appNotificationsEnabled) {
                    Text("Bell + task / mention notifications")
                }
                .onChange(of: appNotificationsEnabled) { _, v in
                    UserDefaults.standard.set(v, forKey: ChannelNotificationManager.appNotificationsEnabledKey)
                }

                Toggle(isOn: $channelNotificationsEnabled) {
                    Text("Starred channel toasts")
                }
                .onChange(of: channelNotificationsEnabled) { _, v in
                    UserDefaults.standard.set(v, forKey: ChannelNotificationManager.enabledKey)
                }

                Toggle(isOn: $channelSoundEnabled) {
                    Text("Play sound for incoming messages")
                }
                .onChange(of: channelSoundEnabled) { _, v in
                    UserDefaults.standard.set(v, forKey: ChannelNotificationManager.soundEnabledKey)
                }
            } header: {
                Text("In-app").font(.subheadline).bold()
            } footer: {
                Text("All on by default. Toggle off to mute Werk completely without changing the system permission. Sound is independent of toasts — keep visual notifications and silence the ting.")
                    .font(.caption).foregroundColor(.secondary)
            }

            Section {
                HStack {
                    Text("System permission")
                    Spacer()
                    Text(permissionStatus).foregroundColor(.secondary)
                }
                HStack {
                    Button("Open System Settings…") {
                        ChannelNotificationManager.shared.openSystemNotificationSettings()
                    }
                    Spacer()
                }

                Toggle(isOn: Binding(
                    get: { !promptSuppressed },
                    set: { newValue in
                        promptSuppressed = !newValue
                        ChannelNotificationManager.shared.promptSuppressed = !newValue
                    }
                )) {
                    Text("Re-ask on launch when notifications are off")
                }
            } header: {
                Text("macOS").font(.subheadline).bold()
            }
        }
        .formStyle(.grouped)
        .task { await refreshStatus() }
    }

    private func refreshStatus() async {
        await withCheckedContinuation { cont in
            ChannelNotificationManager.shared.checkAuthorizationStatus { status in
                permissionStatus = Self.label(for: status)
                cont.resume()
            }
        }
    }

    private static func label(for status: UNAuthorizationStatus) -> String {
        switch status {
        case .authorized: return "Authorized"
        case .denied: return "Denied"
        case .notDetermined: return "Not asked yet"
        case .provisional: return "Provisional"
        case .ephemeral: return "Ephemeral"
        @unknown default: return "Unknown"
        }
    }
}

// MARK: - Account

private struct AccountSettingsTab: View {
    @Environment(AppState.self) private var appState
    @State private var loggingOut = false
    @State private var uploadingAvatar = false
    @State private var avatarError: String?

    var body: some View {
        Form {
            Section {
                HStack(spacing: 12) {
                    SettingsAvatarThumbnail(
                        url: appState.currentUser?.avatarUrl,
                        seed: appState.currentUser?.email ?? "?"
                    )
                    .frame(width: 56, height: 56)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Profile picture")
                            .font(.system(size: 12, weight: .medium))
                        HStack(spacing: 8) {
                            Button {
                                pickAvatar()
                            } label: {
                                HStack(spacing: 6) {
                                    if uploadingAvatar {
                                        ProgressView().controlSize(.small)
                                    }
                                    Text(uploadingAvatar ? "Uploading…" : "Change picture…")
                                }
                            }
                            .disabled(uploadingAvatar)
                        }
                        if let err = avatarError {
                            Text(err).font(.system(size: 10)).foregroundColor(.red)
                        } else {
                            Text("PNG / JPG / HEIC. Max ~5MB.")
                                .font(.system(size: 10)).foregroundColor(.secondary)
                        }
                    }
                    Spacer()
                }
            } header: {
                Text("Picture").font(.subheadline).bold()
            }

            Section {
                LabeledContent("Signed in as") {
                    Text(appState.currentUser?.email ?? "—")
                        .foregroundColor(.secondary)
                        .textSelection(.enabled)
                }
                if let name = appState.currentUser?.name, !name.isEmpty {
                    LabeledContent("Name") {
                        Text(name).foregroundColor(.secondary)
                    }
                }
                LabeledContent("Role") {
                    Text(appState.currentUser?.role ?? "—")
                        .foregroundColor(.secondary)
                }
            } header: {
                Text("Identity").font(.subheadline).bold()
            }

            Section {
                Button(role: .destructive) {
                    Task { await logout() }
                } label: {
                    HStack {
                        if loggingOut { ProgressView().controlSize(.small) }
                        Text(loggingOut ? "Signing out…" : "Sign out")
                    }
                }
                .disabled(loggingOut)
            } footer: {
                Text("Sign out clears the access + refresh tokens stored in Keychain. You'll be returned to the login screen.")
                    .font(.caption).foregroundColor(.secondary)
            }
        }
        .formStyle(.grouped)
    }

    private func logout() async {
        loggingOut = true
        defer { loggingOut = false }
        try? await AuthService.shared.logout()
        await MainActor.run {
            appState.didLogout()
        }
    }

    private func pickAvatar() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.begin { response in
            guard response == .OK, let url = panel.urls.first else { return }
            guard let data = try? Data(contentsOf: url) else {
                Task { @MainActor in avatarError = "Couldn't read \(url.lastPathComponent)" }
                return
            }
            let mime = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "image/jpeg"
            Task { await uploadAvatar(data: data, filename: url.lastPathComponent, mime: mime) }
        }
    }

    private func uploadAvatar(data: Data, filename: String, mime: String) async {
        await MainActor.run {
            uploadingAvatar = true
            avatarError = nil
        }
        defer { Task { @MainActor in uploadingAvatar = false } }
        do {
            let newUrl = try await AuthService.shared.uploadAvatar(
                data: data, filename: filename, mimeType: mime
            )
            await MainActor.run {
                appState.currentUser?.avatarUrl = newUrl
            }
        } catch {
            await MainActor.run {
                avatarError = "Upload failed: \(error.localizedDescription)"
            }
        }
    }
}

/// Small avatar thumbnail used in Settings. Renders a remote image when
/// `url` is set, otherwise a colored initials circle.
private struct SettingsAvatarThumbnail: View {
    let url: String?
    let seed: String

    private var initial: String {
        String(seed.first.map(String.init) ?? "?").uppercased()
    }

    var body: some View {
        Group {
            if let s = url, let u = URL(string: s) {
                AsyncImage(url: u) { phase in
                    switch phase {
                    case .empty: Color.zinc800
                    case .success(let img): img.resizable().scaledToFill()
                    case .failure: initialsCircle
                    @unknown default: initialsCircle
                    }
                }
            } else {
                initialsCircle
            }
        }
        .clipShape(Circle())
        .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 1))
    }

    private var initialsCircle: some View {
        ZStack {
            Color.matcha500
            Text(initial)
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(.white)
        }
    }
}

// MARK: - About

private struct AboutSettingsTab: View {
    private var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—"
    }
    private var buildNumber: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—"
    }
    private var bundleId: String {
        Bundle.main.bundleIdentifier ?? "—"
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("Version") {
                    Text(appVersion).foregroundColor(.secondary).textSelection(.enabled)
                }
                LabeledContent("Build") {
                    Text(buildNumber).foregroundColor(.secondary).textSelection(.enabled)
                }
                LabeledContent("Bundle") {
                    Text(bundleId).foregroundColor(.secondary).textSelection(.enabled).font(.system(size: 11, design: .monospaced))
                }
            } header: {
                Text("Werk").font(.subheadline).bold()
            }

            Section {
                HStack {
                    Spacer()
                    Text("matcharecruit.com")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Spacer()
                }
            }
        }
        .formStyle(.grouped)
    }
}
