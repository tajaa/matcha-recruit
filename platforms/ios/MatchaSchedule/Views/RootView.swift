import SwiftUI
import UIKit
import UserNotifications

struct RootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            switch appState.phase {
            case .restoring:
                LaunchView()
            case .signedOut:
                LoginView()
                    .transition(.opacity)
            case .ready(let profile):
                MainTabs(profile: profile)
                    .transition(.opacity)
            case .needsWeb:
                StatusView(
                    symbol: "person.crop.circle.badge.questionmark",
                    title: "This app is for crew accounts",
                    message: "Managers use Matcha on the web at hey-matcha.com.",
                    actionTitle: "Sign out",
                    action: { await appState.signOut() },
                    link: URL(string: "https://hey-matcha.com")
                )
            case .disabled:
                StatusView(
                    symbol: "calendar.badge.exclamationmark",
                    title: "Scheduling is turned off",
                    message: "Ask your manager to turn on employee scheduling for your company.",
                    actionTitle: "Sign out",
                    action: { await appState.signOut() }
                )
            case .retry(let message):
                StatusView(
                    symbol: "wifi.exclamationmark",
                    title: "Can't reach Matcha",
                    message: message,
                    actionTitle: "Try again",
                    action: { await appState.restore() }
                )
            }
        }
        .animation(.easeInOut(duration: 0.35), value: phaseKey)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onReceive(NotificationCenter.default.publisher(for: .schedulePushTapped)) { notification in
            appState.handlePush(notification.userInfo ?? [:])
        }
        .onReceive(NotificationCenter.default.publisher(for: .schedulePushReceived)) { _ in
            Task { await appState.refreshBadgesIfReady() }
        }
        .onOpenURL { appState.handleURL($0) }
    }

    private var phaseKey: String {
        switch appState.phase {
        case .restoring: "restoring"
        case .signedOut: "signedOut"
        case .ready: "ready"
        case .needsWeb: "needsWeb"
        case .disabled: "disabled"
        case .retry: "retry"
        }
    }
}

// MARK: - Brand mark

private struct BrandMark: View {
    var size: CGFloat = 56

    var body: some View {
        Image(systemName: "leaf.fill")
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(Color.brand, in: RoundedRectangle(cornerRadius: size * 0.24, style: .continuous))
            .accessibilityHidden(true)
    }
}

private struct LaunchView: View {
    var body: some View {
        VStack(spacing: 16) {
            BrandMark(size: 72)
            ProgressView()
            Text("Opening your schedule")
                .font(.app(.subheadline))
                .foregroundStyle(Color.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background { AppBackdrop(vivid: true) }
    }
}

// MARK: - Status

private struct StatusView: View {
    let symbol: String
    let title: String
    let message: String
    var actionTitle: String = "Try again"
    var action: (() async throws -> Void)?
    var link: URL?
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: symbol)
        } description: {
            Text(message)
            if let error { Text(error).foregroundStyle(.red) }
        } actions: {
            if let action {
                Button {
                    busy = true
                    Task {
                        defer { busy = false }
                        do { try await action() } catch { self.error = error.localizedDescription }
                    }
                } label: {
                    if busy { ProgressView() } else { Text(actionTitle) }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy)
            }
            if let link {
                Link("Open hey-matcha.com", destination: link)
            }
        }
        .background { AppBackdrop(vivid: true) }
    }
}

// MARK: - Sign in

/// What the app is for, shown with its own objects: a next shift, an approved
/// swap and an open shift, floating as glass. Decoration, hidden from
/// VoiceOver.
private struct LoginHero: View {
    @State private var shown = false
    @State private var floating = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            // Staggered, not tilted or overlapped: glass cannot see through
            // other glass, and it mis-sizes under a rotation.
            swapNotice
                .offset(x: 50, y: -94 + bob(3))
                .modifier(Arrival(shown: shown, delay: 0.18))
            shiftCard
                .offset(x: -22, y: bob(-4))
                .modifier(Arrival(shown: shown, delay: 0.05))
            openShift
                .offset(x: 44, y: 88 + bob(3))
                .modifier(Arrival(shown: shown, delay: 0.3))
        }
        .frame(maxWidth: .infinity)
        .frame(height: 240)
        .accessibilityHidden(true)
        .task {
            shown = true
            guard !reduceMotion else { return }
            // Started once the pieces have landed: a repeating animation begun
            // in the same pass as their first layout also repeats that layout.
            try? await Task.sleep(for: .seconds(1.4))
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 3.2).repeatForever(autoreverses: true)) { floating = true }
        }
    }

    private func bob(_ amount: CGFloat) -> CGFloat { floating ? amount : -amount }

    private var shiftCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "sunrise.fill").foregroundStyle(.orange)
                Text("TOMORROW").tracking(0.8)
                Spacer()
                Text("in 14h")
            }
            .font(.app(.caption, .semibold))
            .foregroundStyle(Color.secondary)
            Text("6:30 – 2:30 PM")
                .font(.inter(28, .bold))
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text("Barista · Downtown")
                .font(.app(.subheadline))
                .foregroundStyle(Color.secondary)
        }
        .padding(18)
        .frame(width: 264)
        .glassPanel(in: RoundedRectangle(cornerRadius: 26, style: .continuous))
    }

    private var swapNotice: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.app(.title3))
                .foregroundStyle(Color.brand)
            VStack(alignment: .leading, spacing: 1) {
                Text("Swap approved").font(.app(.subheadline, .semibold))
                Text("Saturday is covered").font(.app(.caption)).foregroundStyle(Color.secondary)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .glassPanel(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private var openShift: some View {
        HStack(spacing: 8) {
            Image(systemName: "plus.circle.fill").foregroundStyle(Color.brand)
            Text("Open shift · Fri 4 PM").font(.app(.subheadline, .medium))
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .glassPanel(in: Capsule())
    }

    /// Each piece settles into place in turn; a plain fade under Reduce Motion.
    private struct Arrival: ViewModifier {
        let shown: Bool
        let delay: Double
        @Environment(\.accessibilityReduceMotion) private var reduceMotion

        func body(content: Content) -> some View {
            content
                .opacity(shown ? 1 : 0)
                .scaleEffect(shown || reduceMotion ? 1 : 0.9)
                .offset(y: shown || reduceMotion ? 0 : 24)
                .animation(.spring(response: 0.7, dampingFraction: 0.78).delay(delay), value: shown)
        }
    }
}

private struct LoginView: View {
    private enum Field { case email, password }

    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""
    @State private var revealPassword = false
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focus: Field?

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 10) {
                        BrandMark(size: 34)
                        Text("Matcha Schedule").font(.app(.headline))
                    }
                    .padding(.top, 12)

                    LoginHero()
                        .padding(.top, 20)

                    Spacer(minLength: 20)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Your shifts,\nin your pocket.")
                            .font(.inter(38, .bold))
                            .tracking(-0.6)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Sign in with the work email your manager invited.")
                            .font(.app(.body))
                            .foregroundStyle(Color.secondary)
                    }
                    .padding(.bottom, 24)

                    VStack(spacing: 0) {
                        field(symbol: "envelope") {
                            TextField("Email", text: $email)
                                .textContentType(.username)
                                .keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .submitLabel(.next)
                                .focused($focus, equals: .email)
                                .onSubmit { focus = .password }
                                .accessibilityIdentifier("login.email")
                        }
                        Divider().padding(.leading, 52)
                        field(symbol: "lock") {
                            Group {
                                if revealPassword {
                                    TextField("Password", text: $password)
                                        .accessibilityIdentifier("login.password.visible")
                                } else {
                                    SecureField("Password", text: $password)
                                        .accessibilityIdentifier("login.password")
                                }
                            }
                            .textContentType(.password)
                            .submitLabel(.go)
                            .focused($focus, equals: .password)
                            .onSubmit(submit)
                            Button { revealPassword.toggle() } label: {
                                Image(systemName: revealPassword ? "eye.slash" : "eye")
                                    .foregroundStyle(Color.secondary)
                            }
                            .accessibilityLabel(revealPassword ? "Hide password" : "Show password")
                        }
                    }
                    .glassPanel(in: RoundedRectangle(cornerRadius: 24, style: .continuous))

                    if let error {
                        ErrorRow(message: error)
                            .padding(.top, 14)
                            .padding(.horizontal, 4)
                    }

                    // Never greyed out: with a field still empty, it takes
                    // the employee to that field.
                    Button(action: submit) {
                        LoadingLabel(title: "Sign in", busy: busy)
                            .font(.app(.headline))
                            .padding(.vertical, 6)
                    }
                    .prominentGlassButton()
                    .controlSize(.large)
                    .buttonBorderShape(.capsule)
                    .disabled(busy)
                    .padding(.top, 16)
                    .accessibilityIdentifier("login.submit")
                    // Only when an error appears; clearing it on a retry is not a failure.
                    .sensoryFeedback(trigger: error) { _, new in new == nil ? nil : .error }

                    Text("Can't sign in? Ask your manager to resend your invite.")
                        .font(.app(.footnote))
                        .foregroundStyle(Color.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 16)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 16)
                .frame(minHeight: proxy.size.height)
                .animation(.default, value: error)
            }
            .scrollDismissesKeyboard(.interactively)
            .scrollBounceBehavior(.basedOnSize)
        }
        .background { AppBackdrop(vivid: true) }
    }

    private func field(symbol: String, @ViewBuilder content: () -> some View) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .foregroundStyle(Color.secondary)
                .frame(width: 24)
                .accessibilityHidden(true)
            content()
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 56)
    }

    private func submit() {
        let address = email.trimmingCharacters(in: .whitespaces)
        guard !address.isEmpty else { focus = .email; return }
        guard !password.isEmpty else { focus = .password; return }
        focus = nil
        busy = true
        error = nil
        Task {
            defer { busy = false }
            do { try await appState.signIn(email: address, password: password) }
            catch { self.error = error.localizedDescription }
        }
    }
}

// MARK: - Tabs

private struct MainTabs: View {
    @Environment(AppState.self) private var appState
    let profile: EmployeeProfile

    var body: some View {
        @Bindable var state = appState
        TabView(selection: $state.selectedTab) {
            NavigationStack { ScheduleView(profile: profile) }
                .tabItem { Label("Schedule", systemImage: "calendar") }.tag(0)
            NavigationStack { RequestsView(profile: profile) }
                .tabItem { Label("Requests", systemImage: "arrow.left.arrow.right") }.tag(1)
            InboxListView()
                .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right.fill") }
                .badge(appState.unreadMessages)
                .tag(2)
            NavigationStack { MeView(profile: profile) }
                .tabItem { Label("Me", systemImage: "person.crop.circle.fill") }
                .badge(appState.unreadNotifications)
                .tag(3)
        }
        .tabBarMinimizesOnScroll()
        .sensoryFeedback(.selection, trigger: appState.selectedTab)
    }
}

// MARK: - Me

private struct MeView: View {
    @Environment(AppState.self) private var appState
    let profile: EmployeeProfile
    @AppStorage(AppearancePreference.storageKey) private var appearance = AppearancePreference.system
    @State private var signingOut = false
    @State private var permission: UNAuthorizationStatus?

    var body: some View {
        List {
            GlassHero {
                HStack(spacing: 14) {
                    Avatar(name: profile.displayName, size: 56)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(profile.displayName).font(.app(.title3, .semibold))
                        Text(profile.company_name).font(.app(.subheadline)).foregroundStyle(Color.secondary)
                    }
                }
            }
            .bareRow(top: 8, bottom: 4)

            SectionLabel("Notifications")
            NavigationLink {
                NotificationFeedView()
            } label: {
                Label("Notifications", systemImage: "bell")
                    .badge(appState.unreadNotifications)
            }
            .cardRow()
            .accessibilityIdentifier("me.notifications")
            VStack(alignment: .leading, spacing: 10) {
                LabeledContent {
                    Text(permissionLabel)
                } label: {
                    Label("Push alerts", systemImage: "app.badge")
                }
                if permission == .denied || permission == .notDetermined {
                    Button(permission == .denied ? "Turn on in Settings" : "Turn on push alerts") {
                        if permission == .denied {
                            if let url = URL(string: UIApplication.openSettingsURLString) {
                                UIApplication.shared.open(url)
                            }
                        } else {
                            Task {
                                await PushService.shared.activate()
                                permission = await PushService.shared.authorizationStatus()
                            }
                        }
                    }
                    .buttonStyle(.borderless)
                }
                if let pushError = PushService.shared.lastError {
                    ErrorRow(message: "Push alerts couldn't be set up: \(pushError)")
                }
            }
            .cardRow()

            SectionLabel("Appearance")
            // Buttons rather than a Picker: each option keeps its own
            // identifier for the screen tour.
            HStack(spacing: 6) {
                ForEach(AppearancePreference.allCases) { option in
                    Button { appearance = option } label: {
                        Text(option.label)
                            .font(.app(.subheadline, appearance == option ? .semibold : .regular))
                            .foregroundStyle(appearance == option ? Color(.systemBackground) : Color.primary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background { if appearance == option { Capsule().fill(Color.primary) } }
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.borderless)
                    .accessibilityAddTraits(appearance == option ? .isSelected : [])
                    .accessibilityIdentifier("appearance.\(option.rawValue)")
                }
            }
            .cardRow()
            .sensoryFeedback(.selection, trigger: appearance)

            Button(role: .destructive) {
                signingOut = true
                Task {
                    defer { signingOut = false }
                    // Never fails: offline sign-out clears locally and
                    // queues the server-side revoke for the next launch.
                    await appState.signOut()
                }
            } label: {
                HStack {
                    if signingOut { ProgressView() }
                    Text("Sign out").font(.app(.headline))
                }
                .foregroundStyle(.red)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
            }
            .glassButton()
            .controlSize(.large)
            .buttonBorderShape(.capsule)
            .disabled(signingOut)
            .bareRow(top: 20, bottom: 4)

            Text(versionLine)
                .font(.app(.footnote))
                .foregroundStyle(Color.secondary)
                .frame(maxWidth: .infinity)
                .bareRow(top: 4, bottom: 16)
        }
        .listStyle(.plain)
        .appBackdrop()
        .navigationTitle("Me")
        .task { permission = await PushService.shared.authorizationStatus() }
    }

    private var versionLine: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = info?["CFBundleVersion"] as? String ?? "1"
        return "Matcha Schedule \(version) (\(build))"
    }

    private var permissionLabel: String {
        switch permission {
        case .authorized: "On"
        case .provisional: "Quiet"
        case .ephemeral: "Temporary"
        case .denied: "Off"
        case .notDetermined: "Not set up"
        default: "Checking"
        }
    }
}
