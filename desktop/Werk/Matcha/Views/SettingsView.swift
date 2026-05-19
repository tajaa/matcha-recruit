import SwiftUI
import UserNotifications

/// Macos Settings scene — opened via Cmd+, or the "Werk → Settings…"
/// menu. Three tabs: Notifications, Account, About. Surfaces toggles
/// that were previously only flippable via UserDefaults directly.
struct SettingsView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            NotificationsSettingsTab()
                .tabItem { Label("Notifications", systemImage: "bell") }
            AccountSettingsTab()
                .tabItem { Label("Account", systemImage: "person.circle") }
            AboutSettingsTab()
                .tabItem { Label("About", systemImage: "info.circle") }
        }
        .frame(width: 480, height: 360)
    }
}

// MARK: - Notifications

private struct NotificationsSettingsTab: View {
    /// Mirror the three flags from `ChannelNotificationManager`. Stored
    /// directly in UserDefaults under the same keys the existing send /
    /// observer paths read.
    @State private var appNotificationsEnabled = ChannelNotificationManager.shared.appNotificationsEnabled
    @State private var channelNotificationsEnabled = ChannelNotificationManager.shared.isEnabled
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
                    Text("Channel chat sound + starred toasts")
                }
                .onChange(of: channelNotificationsEnabled) { _, v in
                    UserDefaults.standard.set(v, forKey: ChannelNotificationManager.enabledKey)
                }
            } header: {
                Text("In-app").font(.subheadline).bold()
            } footer: {
                Text("Both are on by default. Toggle off to mute Werk completely without changing the system permission.")
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

    var body: some View {
        Form {
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
