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
                    .transition(.opacity.combined(with: .scale(scale: 1.02)))
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
        .foregroundStyle(Palette.ink)
        .font(TypeScale.body)
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
            .background(RoundedRectangle(cornerRadius: size * 0.3, style: .continuous).fill(Palette.leafGradient))
            .overlay(RoundedRectangle(cornerRadius: size * 0.3, style: .continuous)
                .strokeBorder(Color.white.opacity(0.45), lineWidth: 1))
            .shadow(color: Palette.leaf.opacity(0.4), radius: 14, y: 8)
            .accessibilityHidden(true)
    }
}

private struct LaunchView: View {
    @State private var breathe = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(spacing: 18) {
            BrandMark(size: 72)
                .scaleEffect(breathe ? 1.04 : 0.96)
            Text("Opening your schedule")
                .font(TypeScale.callout)
                .foregroundStyle(Palette.inkSoft)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .ambientBackground(.opener)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) { breathe = true }
        }
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
        VStack(spacing: 20) {
            Spacer()
            VStack(spacing: 16) {
                Image(systemName: symbol)
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(Palette.leaf)
                    .frame(width: 72, height: 72)
                    .background(Palette.leaf.opacity(0.14), in: Circle())
                Text(title).font(TypeScale.title).multilineTextAlignment(.center)
                Text(message).font(TypeScale.body).foregroundStyle(Palette.inkSoft)
                    .multilineTextAlignment(.center)
                if let error { Text(error).font(TypeScale.subhead).foregroundStyle(Palette.alert) }
                if let action {
                    Button {
                        busy = true
                        Task {
                            defer { busy = false }
                            do { try await action() } catch { self.error = error.localizedDescription }
                        }
                    } label: {
                        if busy { ProgressView().tint(.white) } else { Text(actionTitle) }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(busy)
                    .padding(.top, 4)
                }
                if let link {
                    Link("Open hey-matcha.com", destination: link)
                        .font(TypeScale.callout)
                        .foregroundStyle(Palette.leaf)
                }
            }
            .padding(28)
            .glassSurface(cornerRadius: Metrics.heroRadius)
            .rise()
            Spacer()
        }
        .padding(Metrics.gutter)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .ambientBackground()
    }
}

// MARK: - Sign in

private struct LoginView: View {
    private enum Field { case email, password }

    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""
    @State private var revealPassword = false
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focus: Field?

    private var canSubmit: Bool {
        !busy && !email.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 12) {
                    BrandMark(size: 44)
                    Text("Matcha Schedule")
                        .font(.inter(17, .semibold, relativeTo: .headline))
                        .foregroundStyle(Palette.ink)
                }
                .rise()
                .padding(.top, 24)

                Spacer(minLength: 72)

                VStack(alignment: .leading, spacing: 12) {
                    Text("Your shifts,\nin your pocket.")
                        .font(TypeScale.hero)
                        .tracking(-0.8)
                        .foregroundStyle(Palette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Sign in with the work email your manager invited.")
                        .font(TypeScale.body)
                        .foregroundStyle(Palette.inkSoft)
                }
                .rise(delay: 0.06)
                .padding(.bottom, 28)

                VStack(spacing: 12) {
                    GlassField(icon: "envelope.fill", focused: focus == .email) {
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
                    GlassField(icon: "lock.fill", focused: focus == .password) {
                        HStack {
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
                            .onSubmit { if canSubmit { submit() } }
                            Button { revealPassword.toggle() } label: {
                                Image(systemName: revealPassword ? "eye.slash" : "eye")
                                    .foregroundStyle(Palette.inkFaint)
                            }
                            .accessibilityLabel(revealPassword ? "Hide password" : "Show password")
                        }
                    }
                    if let error {
                        ErrorBanner(message: error)
                    }
                    Button(action: submit) {
                        LoadingLabel(title: "Sign in", busy: busy)
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!canSubmit)
                    .padding(.top, 6)
                    .accessibilityIdentifier("login.submit")
                    // Only when an error appears; clearing it on a retry is not a failure.
                    .sensoryFeedback(trigger: error) { _, new in new == nil ? nil : .error }
                }
                .rise(delay: 0.12)

                Text("Can't sign in? Ask your manager to resend your invite.")
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkFaint)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 22)
                    .rise(delay: 0.18)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
            .animation(.spring(response: 0.4, dampingFraction: 0.85), value: error)
        }
        .scrollDismissesKeyboard(.interactively)
        .scrollBounceBehavior(.basedOnSize)
        .ambientBackground(.opener)
    }

    private func submit() {
        focus = nil
        busy = true
        error = nil
        Task {
            defer { busy = false }
            do { try await appState.signIn(email: email.trimmingCharacters(in: .whitespaces), password: password) }
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
        .tint(Palette.leaf)
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
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                profileCard.rise()

                VStack(alignment: .leading, spacing: 10) {
                    SectionTitle(title: "Notifications")
                    VStack(spacing: 0) {
                        NavigationLink {
                            NotificationFeedView()
                        } label: {
                            MeRow(symbol: "bell.fill", tint: Palette.leaf, title: "Notifications") {
                                if appState.unreadNotifications > 0 {
                                    Text("\(appState.unreadNotifications)")
                                        .font(TypeScale.caption).foregroundStyle(.white)
                                        .padding(.horizontal, 8).padding(.vertical, 3)
                                        .background(Palette.leaf, in: Capsule())
                                        .contentTransition(.numericText())
                                }
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(Palette.inkFaint)
                            }
                        }
                        .buttonStyle(PressableStyle())
                        .accessibilityIdentifier("me.notifications")
                        Divider().overlay(Palette.inkFaint.opacity(0.3)).padding(.leading, 52)
                        MeRow(symbol: "app.badge.fill", tint: Palette.dusk, title: "Push alerts") {
                            StatusPill(text: permissionLabel, color: permissionColor)
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
                            .buttonStyle(GlassButtonStyle(tint: Palette.leaf))
                            .padding(.bottom, 12)
                        }
                    }
                    .padding(.horizontal, 14)
                    .glassSurface(elevated: false)
                    if let pushError = PushService.shared.lastError {
                        ErrorBanner(message: "Push alerts couldn't be set up: \(pushError)")
                    }
                }
                .rise(delay: 0.06)

                VStack(alignment: .leading, spacing: 10) {
                    SectionTitle(title: "Appearance")
                    HStack(spacing: 10) {
                        ForEach(AppearancePreference.allCases) { option in
                            AppearanceTile(option: option, selected: appearance == option) {
                                appearance = option
                            }
                        }
                    }
                    .padding(12)
                    .glassSurface(elevated: false)
                    .sensoryFeedback(.selection, trigger: appearance)
                }
                .rise(delay: 0.08)

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
                        if signingOut { ProgressView() } else { Image(systemName: "rectangle.portrait.and.arrow.right") }
                        Text("Sign out")
                    }
                    .font(TypeScale.headline)
                    .foregroundStyle(Palette.alert)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .glassSurface(cornerRadius: 26, elevated: false)
                }
                .buttonStyle(PressableStyle())
                .disabled(signingOut)
                .rise(delay: 0.1)

                Text(versionLine)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkFaint)
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.bottom, 32)
        }
        .scrollIndicators(.hidden)
        .ambientBackground()
        .navigationTitle("Me")
        .task { permission = await PushService.shared.authorizationStatus() }
    }

    private var profileCard: some View {
        HStack(spacing: 16) {
            Avatar(name: profile.displayName, size: 64)
            VStack(alignment: .leading, spacing: 4) {
                Text(profile.displayName).font(TypeScale.title).foregroundStyle(Palette.ink)
                Text(profile.company_name).font(TypeScale.callout).foregroundStyle(Palette.inkSoft)
            }
            Spacer(minLength: 0)
        }
        .padding(20)
        .glassSurface(cornerRadius: Metrics.heroRadius)
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

    private var permissionColor: Color {
        switch permission {
        case .authorized, .provisional, .ephemeral: Palette.leaf
        case .denied: Palette.alert
        default: Palette.inkSoft
        }
    }
}

private struct MeRow<Trailing: View>: View {
    let symbol: String
    let tint: Color
    let title: String
    @ViewBuilder let trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(tint.gradient))
            Text(title).font(TypeScale.callout).foregroundStyle(Palette.ink)
            Spacer()
            trailing()
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}

// MARK: - Appearance picker

/// A miniature of the app in each appearance, the way iOS Settings shows it.
private struct AppearanceTile: View {
    let option: AppearancePreference
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                swatch
                    .frame(height: 92)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(selected ? Palette.leaf : Palette.inkFaint.opacity(0.3),
                                          lineWidth: selected ? 2 : 1)
                    )
                    .shadow(color: Palette.shadow.opacity(selected ? 0.16 : 0.06), radius: 8, y: 4)
                    .scaleEffect(selected ? 1 : 0.96)
                Text(option.label)
                    .font(TypeScale.callout)
                    .foregroundStyle(Palette.ink)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 18))
                    .foregroundStyle(selected ? Palette.leaf : Palette.inkFaint)
                    .contentTransition(.symbolEffect(.replace))
            }
            .frame(maxWidth: .infinity)
            .animation(.spring(response: 0.35, dampingFraction: 0.8), value: selected)
        }
        .buttonStyle(PressableStyle())
        .accessibilityLabel("\(option.label) appearance")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("appearance.\(option.rawValue)")
    }

    @ViewBuilder
    private var swatch: some View {
        switch option {
        case .light: Miniature(dark: false)
        case .dark: Miniature(dark: true)
        case .system: Miniature(dark: false).overlay(Miniature(dark: true).mask(DiagonalHalf()))
        }
    }
}

/// Fixed colors on purpose: each miniature shows its own appearance whatever
/// the phone is currently in.
private struct Miniature: View {
    let dark: Bool

    var body: some View {
        let base = Color(hex: dark ? 0x0A120D : 0xF1F6EC)
        let card = Color(hex: dark ? 0x1D2B22 : 0xFFFFFF)
        let line = Color(hex: dark ? 0x3A4B40 : 0xDCE5D6)
        ZStack(alignment: .topLeading) {
            base
            LinearGradient(colors: [Color(hex: 0x9FD37F, alpha: dark ? 0.25 : 0.45), .clear],
                           startPoint: .topTrailing, endPoint: .center)
            VStack(alignment: .leading, spacing: 6) {
                RoundedRectangle(cornerRadius: 2).fill(line).frame(width: 28, height: 5)
                HStack(spacing: 5) {
                    Capsule().fill(Color(hex: 0xF39A6B)).frame(width: 3)
                    VStack(alignment: .leading, spacing: 4) {
                        RoundedRectangle(cornerRadius: 2).fill(line).frame(width: 30, height: 4)
                        RoundedRectangle(cornerRadius: 2).fill(line.opacity(0.7)).frame(width: 20, height: 4)
                    }
                }
                .padding(7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(card, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                HStack(spacing: 5) {
                    Capsule().fill(Color(hex: 0x7C6CE6)).frame(width: 3)
                    RoundedRectangle(cornerRadius: 2).fill(line).frame(width: 26, height: 4)
                }
                .padding(7)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(card, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
            }
            .padding(9)
        }
    }
}

private struct DiagonalHalf: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
