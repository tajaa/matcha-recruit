import SwiftUI
import UserNotifications
import UniformTypeIdentifiers
import AppKit

/// Macos Settings scene — opened via Cmd+, or the "Werk → Settings…"
/// menu. Three tabs: Notifications, Account, About. Surfaces toggles
/// that were previously only flippable via UserDefaults directly.
struct SettingsView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            NotificationsSettingsTab()
                .tabItem { Label("Notifications", systemImage: "bell") }
            AppearanceSettingsTab()
                .tabItem { Label("Appearance", systemImage: "paintpalette") }
            AccountSettingsTab()
                .tabItem { Label("Account", systemImage: "person.circle") }
            AboutSettingsTab()
                .tabItem { Label("About", systemImage: "info.circle") }
        }
        .frame(width: 480, height: 360)
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
